"""Справочник типов СИ (ОТ) из публичного API АРШИН → PostgreSQL.

Храним только то, что нужно правилам: наименование, обозначение, срок действия,
межповерочные интервалы и методики. Обновляется по требованию (sync) и во время
проверки — для типов, которых ещё нет в базе.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.precheck import ArshinMeth, ArshinMod, ArshinMpi, ArshinType
from app.services.precheck.common import iso

# не более ~2 запросов/сек — ограничение публичного API
_MIN_INTERVAL = 0.55
_lock = asyncio.Lock()
_last_request = 0.0


class ArshinApi:
    """Минимальный клиент eAPI: карточка типа по номеру."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.ARSHIN_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.requests = 0

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
        global _last_request
        async with _lock:
            delta = asyncio.get_running_loop().time() - _last_request
            if delta < _MIN_INTERVAL:
                await asyncio.sleep(_MIN_INTERVAL - delta)
            _last_request = asyncio.get_running_loop().time()
        self.requests += 1
        for attempt in range(3):
            try:
                resp = await client.get(f"{self.base_url}/{path}", params=params,
                                        timeout=self.timeout)
                if resp.status_code == 429 or resp.status_code >= 500:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError:
                if attempt == 2:
                    raise
                await asyncio.sleep(1.5 * (attempt + 1))
        return {}

    async def type_card(self, client: httpx.AsyncClient, ot: str) -> dict | None:
        found = await self._get(client, "mit", {"number": ot, "rows": 3})
        items = (found.get("result") or {}).get("items") or []
        if not items:
            return None
        uuid = items[0].get("mit_uuid")
        card = await self._get(client, f"mit/{uuid}") if uuid else {}
        general = card.setdefault("general", {})
        general.setdefault("mit_uuid", uuid)
        general.setdefault("number", items[0].get("number"))
        general.setdefault("title", items[0].get("title"))
        general.setdefault("notation", items[0].get("notation"))
        return card


def _notation(value: object) -> str | None:
    if isinstance(value, list):
        return "; ".join(str(x) for x in value) or None
    return str(value) if value else None


def _card_fields(card: dict) -> dict:
    g = card.get("general") or {}
    spec_url = next((s.get("doc_url") for s in card.get("spec") or [] if s.get("doc_url")), None)
    return {
        "ot": (g.get("number") or "").strip(),
        "mit_uuid": g.get("mit_uuid"),
        "title": g.get("title"),
        "notation": _notation(g.get("notation")),
        "valid_to": iso(g.get("valid_to")),
        "spec_url": spec_url,
    }


async def save_type(session: AsyncSession, card: dict, source: str | None = None) -> str | None:
    """Записать карточку типа в справочник (заменяя интервалы и методики)."""
    fields = _card_fields(card)
    ot = fields["ot"]
    if not ot:
        return None
    row = await session.get(ArshinType, ot)
    if row is None:
        row = ArshinType(ot=ot)
        session.add(row)
    row.mit_uuid = fields["mit_uuid"]
    row.title = fields["title"]
    row.notation = fields["notation"]
    row.valid_to = fields["valid_to"]
    row.spec_url = fields["spec_url"]
    row.source = source or row.source
    row.updated_at = datetime.utcnow()

    await session.execute(delete(ArshinMpi).where(ArshinMpi.ot == ot))
    for mpi in card.get("mpi") or []:
        session.add(ArshinMpi(
            ot=ot,
            months=mpi.get("mpi"),
            parameter=(mpi.get("parameter") or "").strip() or None,
            valid_from=iso(mpi.get("valid_from")),
            valid_to=iso(mpi.get("valid_to")),
        ))
    await session.execute(delete(ArshinMeth).where(ArshinMeth.ot == ot))
    for meth in card.get("meth") or []:
        session.add(ArshinMeth(
            ot=ot,
            title=meth.get("title"),
            dec_num=meth.get("dec_num"),
            valid_from=iso(meth.get("valid_from")),
            valid_to=iso(meth.get("valid_to")),
        ))
    return ot


async def load_types(session: AsyncSession, ots: list[str]) -> dict[str, dict]:
    """Достать из базы карточки типов в виде, пригодном для правил."""
    if not ots:
        return {}
    result: dict[str, dict] = {}
    rows = (await session.execute(select(ArshinType).where(ArshinType.ot.in_(ots)))).scalars()
    types = {r.ot: r for r in rows}
    if not types:
        return {}
    mpi_rows = (await session.execute(select(ArshinMpi).where(ArshinMpi.ot.in_(types)))).scalars()
    meth_rows = (await session.execute(select(ArshinMeth).where(ArshinMeth.ot.in_(types)))).scalars()
    for t in types.values():
        result[t.ot] = {
            "ot": t.ot,
            "title": t.title,
            "notation": t.notation,
            "valid_to": t.valid_to,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "mpi": [],
            "meth": [],
            "mods": [],
            "aliases": [],
        }
    for m in mpi_rows:
        result[m.ot]["mpi"].append({
            "months": m.months,
            "parameter": m.parameter,
            "valid_from": m.valid_from,
            "valid_to": m.valid_to,
        })
    for m in meth_rows:
        result[m.ot]["meth"].append({
            "title": m.title,
            "dec_num": m.dec_num,
            "valid_from": m.valid_from,
            "valid_to": m.valid_to,
        })
    mod_rows = (await session.execute(
        select(ArshinMod).where(ArshinMod.ot.in_(types)))).scalars()
    for mod in mod_rows:
        result[mod.ot]["mods"].append(mod.name)
    for card in result.values():
        card["mpi"].sort(key=lambda x: (x["months"] is None, x["months"] or 0))
    return result


async def sync_types(
    session: AsyncSession,
    ots: list[str],
    limit: int | None = None,
    source: str = "sync",
) -> dict[str, int]:
    """Дотянуть справочник по списку ОТ. Возвращает статистику."""
    stats = {"requested": len(ots), "saved": 0, "not_found": 0, "errors": 0}
    todo = [ot for ot in dict.fromkeys(o.strip() for o in ots) if ot]
    if limit:
        todo = todo[:limit]
    api = ArshinApi()
    async with httpx.AsyncClient(headers={"User-Agent": "metroCheck-precheck/1.0"}) as client:
        for ot in todo:
            try:
                card = await api.type_card(client, ot)
            except httpx.HTTPError:
                stats["errors"] += 1
                continue
            if not card:
                stats["not_found"] += 1
                continue
            if await save_type(session, card, source=source):
                stats["saved"] += 1
        await session.commit()
    stats["requests"] = api.requests
    return stats


def _is_stale(card: dict, ttl_days: int, now: datetime) -> bool:
    """Карточка устарела, если обновлялась раньше, чем ttl_days назад."""
    if ttl_days <= 0:
        return False
    updated = card.get("updated_at")
    if not updated:
        return True
    try:
        stamp = datetime.fromisoformat(updated)
    except ValueError:
        return True
    return (now - stamp).days >= ttl_days


async def ensure_types(
    session: AsyncSession,
    ots: list[str],
    online: bool = True,
    limit: int = 40,
    ttl_days: int = 7,
) -> tuple[dict[str, dict], dict[str, int]]:
    """Достать карточки типов, обновив отсутствующие и устаревшие (TTL).

    Возвращает (карточки, статистика обновления). TTL нужен, чтобы замечать
    изменения в описании типа — например, новую редакцию методики поверки.
    """
    known = await load_types(session, ots)
    if not online:
        return known, {"missing": 0, "stale": 0, "refreshed": 0}

    now = datetime.utcnow()
    missing = [ot for ot in ots if ot and ot not in known]
    stale = [ot for ot, card in known.items() if _is_stale(card, ttl_days, now)]
    todo = list(dict.fromkeys(missing + stale))
    stats = {"missing": len(missing), "stale": len(stale), "refreshed": 0}
    if not todo:
        return known, stats

    synced = await sync_types(session, todo, limit=min(limit, len(todo)),
                              source="auto: проверка пачки (TTL)")
    stats["refreshed"] = synced.get("saved", 0)
    return await load_types(session, ots), stats


async def sync_mods(
    session: AsyncSession,
    ots: list[str] | None = None,
    limit: int = 50,
) -> dict[str, int]:
    """Скачать описания типов и обновить справочник модификаций."""
    from app.services.precheck.specs import sync_mods_for_type

    stats = {"requested": 0, "saved": 0, "no_spec": 0, "errors": 0}
    query = select(ArshinType).where(ArshinType.spec_url.is_not(None))
    if ots:
        query = query.where(ArshinType.ot.in_(ots))
    types = list((await session.execute(query.limit(limit))).scalars())
    stats["requested"] = len(types)
    async with httpx.AsyncClient(headers={"User-Agent": "metroCheck-precheck/1.0"}) as client:
        for row in types:
            result = await sync_mods_for_type(session, row.ot, row.spec_url or "", client)
            if result["error"]:
                if "не найдены" in result["error"]:
                    stats["no_spec"] += 1
                else:
                    stats["errors"] += 1
            else:
                stats["saved"] += result["saved"]
            await session.commit()
    return stats
