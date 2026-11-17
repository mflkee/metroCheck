"""Московское время: перевод из UTC и пометка (МСК)."""

from datetime import UTC, datetime

from app.utils import fmt_msk, iso_utc, msk_now, to_msk


def test_to_msk_converts_naive_utc():
    # В БД время лежит наивным UTC: 05:29 UTC = 08:29 МСК.
    assert to_msk(datetime(2026, 11, 17, 5, 29)).strftime("%H:%M") == "08:29"


def test_to_msk_keeps_aware_values():
    aware = datetime(2026, 11, 17, 5, 29, tzinfo=UTC)
    assert to_msk(aware).strftime("%H:%M") == "08:29"


def test_fmt_msk_adds_label():
    assert fmt_msk(datetime(2026, 11, 17, 5, 29)) == "17.11.2026 08:29 (МСК)"
    assert fmt_msk(None) == "—"


def test_msk_now_is_moscow_time():
    now = msk_now()
    assert now.utcoffset() is not None
    assert now.utcoffset().total_seconds() == 3 * 3600


def test_iso_utc_marks_timezone():
    assert iso_utc(datetime(2026, 11, 17, 5, 29)) == "2026-11-17T05:29:00+00:00"
    assert iso_utc(None) is None
