"""Извлечение перечня модификаций из «Описания типа» (PDF) и справочник модификаций.

АРШИН не отдаёт модификации в карточке типа, но они есть в описании типа (PDF).
Берём текст, ищем формулировки «имеют следующие модификации …» и сохраняем найденное
как источник `pdf`; вручную подтверждённые записи живут рядом с источником `manual`.
"""

from __future__ import annotations

import io
import re

import httpx
import pdfplumber
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.precheck import ArshinMod
from app.services.precheck.common import norm_text

# «имеют следующие модификации МП2-У, МП3-У, …» / «выпускаются в модификациях …»
_PATTERNS = [
    r"(?:имеют|имеет|выпускаются|изготавливаются)\s+(?:следующие\s+)?модификаци\w*[:\s]+([^.;]{10,600})",
    r"модификации[:\s]+([^.;]{10,600})",
    r"исполнени\w*[:\s]+([^.;]{10,600})",
]

_STOP_WORDS = {"нет", "модификации", "исполнения", "модификация", "исполнение", "-"}


def parse_modifications(text: str) -> list[str]:
    """Вытащить список модификаций из текста описания типа."""
    flat = re.sub(r"\s+", " ", text)
    for pattern in _PATTERNS:
        found: list[str] = []
        for match in re.finditer(pattern, flat, re.I):
            chunk = match.group(1)
            for token in re.split(r",|;", chunk):
                token = token.strip(" .:«»\"'()")
                if not (1 < len(token) < 60):
                    continue
                if norm_text(token) in {norm_text(w) for w in _STOP_WORDS}:
                    continue
                if not re.search(r"[А-Яа-яA-Za-z]", token):
                    continue
                if token not in found:
                    found.append(token)
            if len(found) >= 2:
                return found[:40]
    return []


async def extract_from_pdf(data: bytes) -> list[str]:
    """Прочитать PDF описания типа и вернуть модификации."""

    def _run() -> str:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages[:8])

    import asyncio

    text = await asyncio.to_thread(_run)
    return parse_modifications(text)


async def sync_mods_for_type(
    session: AsyncSession,
    ot: str,
    spec_url: str,
    client: httpx.AsyncClient,
) -> dict:
    """Скачать описание типа и сохранить найденные модификации."""
    stats = {"ot": ot, "saved": 0, "error": ""}
    try:
        resp = await client.get(spec_url, timeout=60)
        resp.raise_for_status()
        names = await extract_from_pdf(resp.content)
    except Exception as exc:  # noqa: BLE001
        stats["error"] = str(exc)[:120]
        return stats

    if not names:
        stats["error"] = "модификации в описании типа не найдены"
        return stats

    await session.execute(
        delete(ArshinMod).where(ArshinMod.ot == ot, ArshinMod.source == "pdf"))
    for name in names:
        session.add(ArshinMod(ot=ot, name=name, source="pdf"))
    stats["saved"] = len(names)
    return stats


async def load_mods(session: AsyncSession, ots: list[str]) -> dict[str, list[str]]:
    """Модификации по списку типов."""
    if not ots:
        return {}
    rows = (await session.execute(
        select(ArshinMod).where(ArshinMod.ot.in_(ots)))).scalars()
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row.ot, []).append(row.name)
    return out
