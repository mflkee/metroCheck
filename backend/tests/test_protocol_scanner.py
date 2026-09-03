"""Tests for PDF text normalization (pdfplumber (cid:N) artifacts) and MIT number extraction."""

import re

from app.services.protocol_extraction_service import ProtocolExtractionService
from app.services.protocol_scanner import _normalize_pdf_text


def _extract_mit(text: str) -> str | None:
    return ProtocolExtractionService()._extract_mit_number(text)


def test_normalize_strips_cid_glyph_codes():
    assert _normalize_pdf_text("65(cid:9)554-16") == "65554-16"
    assert _normalize_pdf_text("74(cid:9)748-19\n") == "74748-19\n"


def test_mit_number_recovers_kerned_multi_digit():
    """pdfplumber breaks kerned MIT numbers: 65554-16 -> 65(cid:9)554-16."""
    raw = (
        "наименование, тип (согласно Государственного реестра СИ РФ)\n"
        "65(cid:9)554-16\n"
        "номер по Государственному реестру СИ РФ\n"
        "Заводской номер (номера): 4810984\n"
        "Средства поверки:\n"
        "77090-19; Преобразователи давления эталонные\n"
    )
    cleaned = _normalize_pdf_text(raw)
    assert _extract_mit(cleaned) == "65554-16"


def test_mit_number_does_not_pick_etalon_from_sredstva_poverki():
    """Without cleanup, regex picks a foreign number from 'Средства поверки' (77090-19);
    the fix (strip (cid:N)) makes it recover the real MIT number."""
    raw = (
        "наименование, тип (согласно Государственного реестра СИ РФ)\n"
        "65(cid:9)554-16\n"
        "номер по Государственному реестру СИ РФ\n"
        "Заводской номер (номера): 4810984\n"
        "Средства поверки:\n"
        "77090-19; Преобразователи давления эталонные\n"
    )
    assert _extract_mit(raw) == "77090-19"
    assert _extract_mit(_normalize_pdf_text(raw)) == "65554-16"
