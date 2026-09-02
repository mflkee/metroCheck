"""Unit tests for deterministic MIT number (ОТ) extraction."""

from app.services.ai_extraction_service import (
    _extract_mit_number_deterministic,
    _prepare_mit_number,
)


def test_section_gosreestr_first_match():
    text = (
        "Средство измерений: Манометр\n"
        "Номер в государственном реестре: 74748-19\n"
        "Методика поверки МП 73828-19\n"
    )
    assert _extract_mit_number_deterministic(text) == "74748-19"


def test_section_registration_number():
    text = "Регистрационный номер типа СИ: 65554-16\nЗав. № 0001"
    assert _extract_mit_number_deterministic(text) == "65554-16"


def test_section_reestr_si():
    text = "Реестр СИ: 77090-19\nПротокол № 12/081/25"
    assert _extract_mit_number_deterministic(text) == "77090-19"


def test_labeled_type_si():
    text = "Тип средства измерений 47279-11, сертификат 12345"
    assert _extract_mit_number_deterministic(text) == "47279-11"


def test_fallback_first_number():
    text = "Протокол № 12/081/25, номер методики 73828-19"
    assert _extract_mit_number_deterministic(text) == "73828-19"


def test_no_number_returns_none():
    assert _extract_mit_number_deterministic("без номеров") is None
    assert _extract_mit_number_deterministic(None) is None


def test_prepare_mit_number_norm():
    data = {"mit_number": "№ 65967-17 МП"}
    prepared = _prepare_mit_number(data)
    assert prepared["mit_number"] == "65967-17"


def test_prepare_mit_number_removes_garbage():
    data = {"mit_number": "не найдено"}
    prepared = _prepare_mit_number(data)
    assert "mit_number" not in prepared
