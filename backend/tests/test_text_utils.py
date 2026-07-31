"""Unit tests for text normalization helpers."""

from app.utils.text import normalize_verifier


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
