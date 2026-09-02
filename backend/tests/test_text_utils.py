"""Unit tests for text normalization helpers."""

from app.utils.text import format_verifier, normalize_verifier


def test_verifier_case_insensitive():
    assert normalize_verifier("Большаков С.Н.") == "большаков с.н."


def test_verifier_missing_trailing_dot_lowercase():
    """Extraction stores lowercase; trailing dot must still be normalized."""
    assert normalize_verifier("большаков с.н") == "большаков с.н."


def test_verifier_capitalized_missing_trailing_dot():
    assert normalize_verifier("Большаков С.Н") == "большаков с.н."


def test_verifier_spaces_around_dots():
    assert normalize_verifier("Кадыков П. Ю.") == "кадыков п.ю."


def test_verifier_match_across_sources():
    """LK (proper case) must match extracted protocol (lowercase, no dot)."""
    assert normalize_verifier("Большаков С.Н.") == normalize_verifier("большаков с.н")


def test_verifier_empty():
    assert normalize_verifier(None) == ""
    assert normalize_verifier("") == ""
    assert normalize_verifier("   ") == ""


def test_format_verifier_lowercase():
    assert format_verifier("чупин а.а.") == "Чупин А.А."


def test_format_verifier_proper_case_preserved():
    assert format_verifier("Большаков С.Н.") == "Большаков С.Н."


def test_format_verifier_uppercase_normalized():
    assert format_verifier("КАДЫКОВ П.Ю.") == "Кадыков П.Ю."


def test_format_verifier_no_trailing_dot():
    assert format_verifier("большаков с.н") == "Большаков С.Н."


def test_format_verifier_spaces_around_dots():
    assert format_verifier("Кадыков П. Ю.") == "Кадыков П.Ю."


def test_format_verifier_empty():
    assert format_verifier(None) == ""
    assert format_verifier("") == ""


def test_format_verifier_does_not_affect_comparison():
    formatted = format_verifier("Чупин А.А.")
    assert normalize_verifier(formatted) == normalize_verifier("чупин а.а")
