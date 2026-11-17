"""Извлечение перечня модификаций из «Описания типа» (PDF) и справочник модификаций.

АРШИН не отдаёт модификации в карточке типа, но они есть в описании типа (PDF).
Разбор идёт в два прохода:

1. по строкам — ищем заголовок «Датчики имеют следующие модели/модификации/исполнения»
   и собираем строки-пункты после него (основной путь: так перечни свёрстаны в
   большинстве описаний, включая табличные списки моделей);
2. по тексту — старый вариант с регулярками на случай перечня внутри абзаца
   («выпускаются в модификациях МП2-У, МП3-У, …»).

Найденное сохраняется как источник `pdf`; вручную подтверждённые записи живут рядом
с источником `manual`.
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

# заголовок перечня: «Датчики имеют следующие модели …», «выпускаются в модификациях …»
_HEADER = re.compile(
    r"(?:имеют|имеет|выпускаются|изготавливаются|поставляются)\s+"
    r"(?:следующие\s+)?(?:модели|модификации|исполнения)\w*",
    re.I,
)
_HEADER_SHORT = re.compile(r"^\s*(?:модели|модификации|исполнения)\s*[:\-–—]\s*", re.I)

# начало следующего раздела описания — перечень закончился
_SECTION = re.compile(
    r"^\s*(?:лист\s*№|таблица\s*\d|рисунок\s*\d|техническ|метрологическ|"
    r"знак утверждения|комплектность|поверка\b|нормальные условия|"
    r"условия эксплуатации|общий вид|датчики\b|приборы\b|каждая\b|"
    r"средства измерений\b|место нанесения|предназначен)",
    re.I,
)

# пункт перечня: «-150TG/150TGR - модели …», «• МП3-У — …», «1) МП4-У»
_BULLET = re.compile(r"^\s*(?:[-–—•·*]|\d+[.)])\s*")
# пояснение после обозначения: « - модель …», «-модель …», « — прибор …»
# (только строчная буква: «МП2-У» — это часть обозначения, а не пояснение)
_EXPLAIN = re.compile(r"\s*[-–—]\s*(?=[а-яё])")
# допустимые символы в обозначении модификации
_CODE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9./\-]*$")

# старые регулярки для перечня внутри абзаца
_PATTERNS = [
    r"(?:имеют|имеет|выпускаются|изготавливаются|поставляются)\s+(?:следующие\s+)?модификаци\w*[:\s]+([^.;]{10,600})",
    r"модификаци\w*[:\s]+([^.;]{10,600})",
    r"исполнени\w*[:\s]+([^.;]{10,600})",
]

# фразы, после которых перечисление модификаций заканчивается
_LIST_END = re.compile(
    r"\b(?:выпускаются|изготавливаются|поставляются|имеют|имеет|отличаются)\b", re.I)

_STOP_WORDS = {"нет", "модификации", "исполнения", "модификация", "исполнение",
               "модели", "модель", "-"}
_STOP_NORM = {norm_text(word) for word in _STOP_WORDS}

# признаки текста описания, а не обозначения модификации
_PROSE = re.compile(
    r"\b(?:котор\w*|соответств\w*|различа\w*|отлича\w*|метрологическ\w*|"
    r"нормированн\w*|эксплуатационн\w*|взрывонепроницаем\w*|взрывозащит\w*|"
    r"измеряем\w*|предназначен\w*|применя\w*|использу\w*|входящ\w*|встроенн\w*|"
    r"явля\w*|предел\w*|циферблат\w*|индикатор\w*|процессор\w*|погрешност\w*|"
    r"исполнени\w*|модификаци\w*|модел\w*|сенсор\w*|модул\w*|антенн\w*|"
    r"индикаци\w*|наличи\w*|типом|длиной|уровня|температур\w*|вибро\w*|оптическ\w*|"
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


def _valid_code(token: str) -> bool:
    """Похоже ли значение на обозначение модификации (одно слово, без единиц)."""
    token = token.strip()
    if not (1 < len(token) < 60):
        return False
    if "±" in token or " " in token or not _CODE.fullmatch(token):
        return False
    if not re.search(r"[А-ЯЁA-Z]", token):  # «12345» — не обозначение
        return False
    if norm_text(token) in _STOP_NORM:
        return False
    return not _looks_like_prose(token)


def _codes(value: str) -> list[str]:
    """Разбить «150TG/150TGR» на отдельные обозначения и отфильтровать мусор."""
    out: list[str] = []
    for part in value.split("/"):
        part = part.strip(" .:;«»\"'()")
        if _valid_code(part):
            out.append(part)
    return out


def _entry_codes(line: str) -> list[str]:
    """Обозначения из одной строки-пункта перечня."""
    text = _BULLET.sub("", line.strip())
    # «-150CG-модель для …» / «150TG/150TGR - модели …»
    text = _EXPLAIN.split(text)[0]
    text = text.strip(" .:;«»\"'()")
    if not text:
        return []
    first = text.split()[0]
    return _codes(first)


def _from_lines(text: str) -> list[str]:
    """Собрать перечень из строк-пунктов после заголовка."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not (_HEADER.search(line) or _HEADER_SHORT.match(line)):
            continue
        found: list[str] = []
        for next_line in lines[index + 1:index + 81]:
            if not next_line.strip():
                continue
            if not _BULLET.match(next_line):
                # перечень кончился: пошёл новый раздел/таблица/абзац
                if _SECTION.match(next_line):
                    break
                continue
            for code in _entry_codes(next_line):
                if code not in found:
                    found.append(code)
            if len(found) >= 40:
                break
        if found:
            return found[:40]
    return []


def _from_inline(text: str) -> list[str]:
    """Старый путь: перечень внутри абзаца («выпускаются в модификациях …»)."""
    flat = re.sub(r"\s+", " ", text)
    for pattern in _PATTERNS:
        found: list[str] = []
        for match in re.finditer(pattern, flat, re.I):
            chunk = match.group(1)
            # строки таблиц («±0,0754), ±0,10») — не перечень модификаций
            if "±" in chunk:
                continue
            # обрезаем хвост вида «… ВП4-У выпускаются с 2015 года»
            chunk = _LIST_END.split(chunk)[0]
            for token in re.split(r",|;", chunk):
                token = _EXPLAIN.split(_BULLET.sub("", token.strip()))[0]
                token = token.strip(" .:«»\"'()")
                if not token:
                    continue
                parts = _codes(token) if " " not in token else _codes(token.split()[0])
                for code in parts:
                    if code not in found:
                        found.append(code)
            if len(found) >= 2:
                return found[:40]
    return []


def parse_modifications(text: str) -> list[str]:
    """Вытащить список модификаций из текста описания типа."""
    return _from_lines(text) or _from_inline(text)


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
        # не трогаем прошлый разбор: пустой результат чаще всего означает,
        # что PDF не распознался, а не что модификаций нет
        stats["error"] = "модификации в описании типа не найдены"
        return stats

    # описание скачано и прочитано: старый перечень заменяем целиком,
    # иначе мусор от прошлого разбора останется в справочнике
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
