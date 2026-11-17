"""Сверка с уже опубликованными записями АРШИН."""

from app.services.precheck.rules import ERROR, WARNING, Context, rule_published


def _row(**overrides):
    row = {
        "row": 2,
        "ot": "24116-13",
        "mi_number": "4054183",
        "vrf_date": "2026-11-17",
        "valid_date": "2031-11-16",
        "docnum": "С-ЕЖБ/17-11-2026/123456789",
    }
    row.update(overrides)
    return row


def test_published_local_match_is_warning():
    """Свидетельство уже есть в нашей базе — повторная загрузка создаст дубль."""
    ctx = Context(published={_row()["docnum"]: {
        "ot": "24116-13",
        "mi_number": "4054183",
        "vrf_date": "2026-11-17",
        "valid_date": "2031-11-16",
    }})
    issues = rule_published(_row(), ctx)
    assert len(issues) == 1
    assert issues[0].level == WARNING
    assert "уже опубликовано" in issues[0].message
    assert "дубль" in issues[0].message


def test_published_lk_match_is_warning():
    """Записи нет в нашей базе, но она найдена в ЛК АРШИН по свидетельству."""
    ctx = Context(lk_published={_row()["docnum"]: {"id": 123}})
    issues = rule_published(_row(), ctx)
    assert len(issues) == 1
    assert issues[0].level == WARNING
    assert "по данным ЛК" in issues[0].message


def test_published_mismatch_is_error():
    ctx = Context(published={_row()["docnum"]: {
        "ot": "24116-13",
        "mi_number": "4054183",
        "vrf_date": "2025-11-17",
        "valid_date": "2030-11-16",
    }})
    issues = rule_published(_row(), ctx)
    assert len(issues) == 1
    assert issues[0].level == ERROR
    assert "расходится" in issues[0].message


def test_published_without_docnum_is_silent():
    ctx = Context(published={"X": {"ot": "24116-13"}})
    assert rule_published(_row(docnum=""), ctx) == []


def test_published_by_arshin_url():
    """Ссылка на запись АРШИН в строке — тоже повод предупредить."""
    ctx = Context(existing_records={"1-443771055": {"result": {}}})
    issues = rule_published(
        _row(docnum="", arshin_url="https://fgis.gost.ru/fundmetrology/eapi/vri/1-443771055"),
        ctx,
    )
    assert len(issues) == 1
    assert issues[0].level == WARNING
    assert "по ссылке" in issues[0].message

