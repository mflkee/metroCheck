"""Московское время для отображения: всё показываем в МСК с пометкой (МСК)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

TIME_FMT = "%d.%m.%Y %H:%M"
DATE_FMT = "%d.%m.%Y"


def msk_now() -> datetime:
    """Текущее время в Москве (aware)."""
    return datetime.now(MSK)


def to_msk(value: datetime) -> datetime:
    """Перевести время в МСК. Наивные значения считаем UTC (так они пишутся в БД)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(MSK)


def fmt_msk(value: datetime | None, fmt: str = TIME_FMT) -> str:
    """Отформатировать время в МСК с пометкой: «17.11.2026 12:15 (МСК)»."""
    if value is None:
        return "—"
    return f"{to_msk(value).strftime(fmt)} (МСК)"


def fmt_msk_now(fmt: str = TIME_FMT) -> str:
    """Текущее московское время с пометкой."""
    return f"{msk_now().strftime(fmt)} (МСК)"


def iso_utc(value: datetime | None) -> str | None:
    """ISO-строка с явным UTC, чтобы браузер не принял её за местное время."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()
