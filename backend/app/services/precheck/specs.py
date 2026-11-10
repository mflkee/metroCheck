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
    r"(?:имеют|имеет|выпускаются|изготавливаются|поставляются)\s+(?:следующие\s+)?модификаци\w*[:\s]+([^.;]{10,600})",
    r"модификаци\w*[:\s]+([^.;]{10,600})",
    r"исполнени\w*[:\s]+([^.;]{10,600})",
]

# фразы, после которых перечисление модификаций заканчивается
_LIST_END = re.compile(
    r"\b(?:выпускаются|изготавливаются|поставляются|имеют|имеет|отличаются)\b", re.I)

_STOP_WORDS = {"нет", "модификации", "исполнения", "модификация", "исполнение", "-"}

# признаки текста описания, а не обозначения модификации
_PROSE = re.compile(
    r"\b(?:котор\w*|соответств\w*|различа\w*|отлича\w*|метрологическ\w*|"
    r"нормированн\w*|эксплуатационн\w*|взрывонепроницаем\w*|взрывозащит\w*|"
    r"измеряем\w*|предназначен\w*|применя\w*|использу\w*|входящ\w*|встроенн\w*|"
    r"явля\w*|предел\w*|циферблат\w*|индикатор\w*|процессор\w*|погрешност\w*|"
    r"исполнени\w*|модификаци\w*|сенсор\w*|модул\w*|антенн\w*|индикаци\w*|"
    r"наличи\w*|типом|длиной|уровня|температур\w*|вибро\w*|оптическ\w*|"
    r"триплекс|техническ\w*)\b",
    re.I,
)


def _looks_like_prose(token: str) -> bool:
    """Отличить обозначение модификации от фразы из описания типа.

    В описаниях перечень часто перемешан с пояснениями («которые различаются
    быстродействием процессора», «по ГОСТ Р 52931-2008»). Такие фразы в справочник
    попадать не должны: они дают ложные подсказки.
    """
    if _PROSE.search(token):
        return True
    if token[:1].islower():  # обозначения начинаются с заглавной буквы или цифры
        return True
    return "ГОСТ" in token.upper()


def parse_modifications(text: str) -> list[str]:
    """Вытащить список модификаций из текста описания типа."""
    flat = re.sub(r"\s+", " ", text)
    stop = {norm_text(w) for w in _STOP_WORDS}
    for pattern in _PATTERNS:
        found: list[str] = []
        for match in re.finditer(pattern, flat, re.I):
            chunk = match.group(1)
            # обрезаем хвост вида «… ВП4-У выпускаются с 2015 года»
            chunk = _LIST_END.split(chunk)[0]
            for token in re.split(r",|;", chunk):
                # «ТБ-1Р (модификации ТБ-1Р» → «ТБ-1Р»: хвост в скобках — пояснение
                token = re.sub(r"\s*\(.*$", "", token)
                token = token.strip(" .:«»\"'()")
                if not (1 < len(token) < 60):
                    continue
                if len(token.split()) > 3:
                    continue
                if norm_text(token) in stop:
                    continue
                if not re.search(r"[А-Яа-яA-Za-z]", token):
                    continue
                if _looks_like_prose(token):
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

    # описание скачано и прочитано: старый перечень заменяем целиком,
    # иначе мусор от прошлого разбора останется в справочнике
    await session.execute(
        delete(ArshinMod).where(ArshinMod.ot == ot, ArshinMod.source == "pdf"))
    if not names:
        stats["error"] = "модификации в описании типа не найдены"
        return stats

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
