"""Общие утилиты проверки: нормализация значений, даты, МПИ."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta


def empty(value: object) -> bool:
    """Пустое ли значение (None, пустая строка, пустой список)."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict)):
        return len(value) == 0
    return False


def norm_text(value: str | None) -> str:
    """Для сравнения текстов: верхний регистр без пунктуации и пробелов."""
    s = (value or "").upper().replace("Ё", "Е")
    return re.sub(r"[\s\-–—_.,;:()]+", "", s)


def norm_number(value: object) -> str:
    """Нормализация заводского номера.

    В реестре встречаются непечатаемые символы (U+FFFC), разные регистры,
    кириллица/латиница в похожих буквах, пробелы и дефисы.
    """
    if value is None:
        return ""
    s = str(value)
    s = s.replace("\ufffc", "").replace("\u200b", "").replace("\ufeff", "")
    s = s.replace("№", "").strip().upper()
    s = s.translate(str.maketrans("ABCEHKMOPTXY", "АВСЕНКМОРТХУ"))
    s = re.sub(r"[\s\-–—/\\.,;:]+", "", s)
    return unicodedata.normalize("NFKC", s)


def iso(value: object) -> str | None:
    """Привести дату к ISO: date/datetime, «ДД.ММ.ГГГГ», «ГГГГ-ММ-ДД», серийный номер Excel."""
    if value in (None, "", 0):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        try:
            return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
        except (OverflowError, ValueError):
            return None
    s = str(value).strip()
    if re.fullmatch(r"\d{4,6}", s):
        try:
            return (date(1899, 12, 30) + timedelta(days=int(s))).isoformat()
        except (OverflowError, ValueError):
            return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return m.group(0) if m else None


def norm_condition(value: object) -> str:
    """«24,5 °С» → «24.5»; «101,9 кПа» → «101.9»."""
    s = str(value or "").replace(",", ".").replace("\xa0", " ")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return m.group(0) if m else ""


def add_months(day: str, months: int) -> str:
    y, m, d = map(int, day.split("-"))
    m2 = m - 1 + months
    y2, m2 = y + m2 // 12, m2 % 12 + 1
    for candidate in (d, 30, 29, 28):
        try:
            return date(y2, m2, candidate).isoformat()
        except ValueError:
            continue
    return date(y2, m2, 28).isoformat()


def mpi_valid_until(vrf: str, months: int) -> str:
    """Действительно до = дата поверки + МПИ − 1 день."""
    return (date.fromisoformat(add_months(vrf, months)) - timedelta(days=1)).isoformat()


def used_months(vrf: str, valid: str) -> int | None:
    """Сколько месяцев фактически применили."""
    for n in range(1, 121):
        if mpi_valid_until(vrf, n) == valid:
            return n
    return None


def levenshtein(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def meth_core(value: str | None) -> tuple[str, str]:
    """«МП 83-221- 2016 с изменением № 2» → ("МП832212016", "2")."""
    s = (value or "").upper().replace("Ё", "Е")
    edition = ""
    m = re.search(r"№\s*(\d+)", s)
    if m:
        edition = m.group(1)
    base = re.split(r"С\s*ИЗМ", s)[0]
    base = re.sub(r"[^0-9A-ZА-Я]+", "", base)
    return base, edition
