"""Text normalization helpers."""

import re


def normalize_verifier(name: str | None) -> str:
    """Normalize verifier name for comparison.

    Handles common OCR/protocol variations:
    - removes leading/trailing whitespace
    - removes spaces around dots in initials
    - adds missing trailing dot after last initial
    - lower-cases for case-insensitive comparison
    """
    if not name:
        return ""
    name = name.strip()
    # Remove spaces around dots: "Т. Е." -> "Т.Е."
    name = re.sub(r"\s*\.\s*", ".", name)
    # Add trailing dot after last initial if missing: "Большаков С.Н" -> "Большаков С.Н.",
    # also works for already-lowercased names (extraction stores lowercase)
    name = re.sub(r"(?<=[\s.])([А-Яа-яA-Za-z])$", r"\1.", name)
    return name.lower()
