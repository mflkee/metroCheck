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


def format_verifier(name: str | None) -> str:
    """Format verifier name for display: capital surname + uppercase initials.

    Display-only helper; comparison must still go through normalize_verifier().
    Examples:
        "чупин а.а."  -> "Чупин А.А."
        "Большаков с.н" -> "Большаков С.Н."
    """
    if not name:
        return ""
    tokens = [t for t in name.replace(",", " ").split() if t]
    if not tokens:
        return ""
    surname = "-".join(
        seg[:1].upper() + seg[1:].lower() for seg in tokens[0].split("-") if seg
    )
    initials_tokens: list[str] = []
    for tok in tokens[1:]:
        letters = re.findall(r"[A-Za-zА-Яа-яЁё]", tok)
        if letters and len(letters) <= 2:
            initials_tokens.append("".join(f"{l.upper()}." for l in letters))
        else:
            initials_tokens.append(" " + tok[:1].upper() + tok[1:].lower())
    initials = "".join(initials_tokens).strip()
    return f"{surname} {initials}".strip()
