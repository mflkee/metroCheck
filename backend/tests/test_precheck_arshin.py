"""Дубли и действующие поверки по публичным данным АРШИН."""

from app.services.precheck.rules import WARNING, Context, rule_arshin_existing


def _row(**overrides):
    row = {
        "row": 54,
        "ot": "24116-13",
        "mi_number": "4054183",
        "vrf_date": "2026-11-10",
        "valid_date": "2031-11-09",
    }
    row.update(overrides)
    return row


def _ctx(records, previous=None):
    return Context(
        arshin_records={("24116-13", "4054183"): records},
        previous={("24116-13", "4054183"): previous or []},
    )


def test_same_record_is_warning():
    ctx = _ctx([{
        "org": "ООО «МКАИР»", "vrf_date": "2026-11-10",
        "valid_date": "2031-11-09", "docnum": "С-ЕЖБ/10-11-2026/1",
    }])
    issues = rule_arshin_existing(_row(docnum="С-ЕЖБ/10-11-2026/1"), ctx)
    assert issues and issues[0].level == WARNING
    assert "уже опубликована" in issues[0].message
    assert "МКАИР" in issues[0].message


def test_active_previous_verification_is_warning():
    """Старая запись другого поверителя действует до 06.12.2026, новая — 10.11.2026."""
    ctx = _ctx([{
        "org": "ООО «Автоматизация и метрология»", "vrf_date": "2023-12-07",
        "valid_date": "2026-12-06", "docnum": "ГПМ.А-1",
    }])
    issues = rule_arshin_existing(_row(), ctx)
    assert issues and issues[0].level == WARNING
    assert "действующая поверка" in issues[0].message
    assert "06.12.2026" in issues[0].message


def test_expired_previous_verification_is_silent():
    ctx = _ctx([{
        "org": "ООО «Автоматизация и метрология»", "vrf_date": "2020-12-07",
        "valid_date": "2025-12-06", "docnum": "ГПМ.А-1",
    }])
    assert rule_arshin_existing(_row(), ctx) == []


def test_record_known_locally_is_left_to_local_rules():
    ctx = _ctx(
        [{"org": "ООО «МКАИР»", "vrf_date": "2026-11-10",
          "valid_date": "2031-11-09", "docnum": "С-ЕЖБ/10-11-2026/1"}],
        previous=[{"vrf_date": "2026-11-10", "valid_date": "2031-11-09"}],
    )
    assert rule_arshin_existing(_row(), ctx) == []
