"""Standalone test runner for protocol extraction — runs inside backend container.

Usage (inside metroCheck_backend container):
    TEST_DIR=/test_protocols OUTPUT_PATH=/reports/parsed_test_sample.xlsx \
        python backend/scripts/run_extraction_test.py

The runner scans all PDFs under TEST_DIR, runs regex-only extraction (AI disabled),
and writes an Excel report to OUTPUT_PATH for manual review.
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, "/app")

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from app.services.protocol_extraction_service import ProtocolExtractionService
from app.services.protocol_scanner import ProtocolScanner

TEST_DIR = Path(os.environ.get("TEST_DIR", "/test_protocols"))
OUTPUT_PATH = Path(os.environ.get("OUTPUT_PATH", "/reports/parsed_test_sample.xlsx"))


class NoAiExtractionService(ProtocolExtractionService):
    """Regex-only extraction service that skips AI fallback."""

    async def _ai_extract_fields(self, text: str, fields: list[str]) -> dict[str, str]:
        return {}


def run_extraction(pdf_path: Path) -> tuple[str, dict]:
    scanner = ProtocolScanner(db=None, protocols_base_path="/")
    ocr_result = scanner.extract_text_sync(str(pdf_path))
    text = ocr_result.get("text", "")

    service = NoAiExtractionService()
    result = asyncio.run(service.extract(text, pdf_path.name, str(pdf_path)))
    return text, result


def auto_fit_columns(ws) -> None:
    for column_cells in ws.columns:
        length = max(len(str(cell.value or "")) for cell in column_cells)
        ws.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 60)


def main() -> None:
    files = sorted(f for f in TEST_DIR.iterdir() if f.suffix.lower() == ".pdf")
    print(f"Found {len(files)} PDF files in {TEST_DIR}")

    wb = Workbook()
    ws = wb.active
    ws.title = "Parsed Protocols"

    headers = [
        "№",
        "Файл",
        "№ протокола",
        "Наименование",
        "Тип",
        "Зав№",
        "№ОТ",
        "Методика",
        "Год",
        "Владелец",
        "Дата",
        "Поверитель",
        "t, °C",
        "φ, %",
        "P, кПа",
        "Диапазон",
        "Статус",
        "Confidence",
        "Страниц",
        "Ошибка OCR",
        "Raw text (first 300 chars)",
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, pdf_path in enumerate(files, 1):
        print(f"[{idx}/{len(files)}] Processing {pdf_path.name} ...")
        try:
            text, result = run_extraction(pdf_path)
            data = result.get("content", {}) or {}
            ocr_pages = 0
            ocr_error = ""

            # Quick re-sync scan just to get pages/error without DB
            scanner = ProtocolScanner(db=None, protocols_base_path="/")
            sync_res = scanner.extract_text_sync(str(pdf_path))
            ocr_pages = sync_res.get("pages", 0)
            ocr_error = sync_res.get("error", "") or ""

            ws.append(
                [
                    idx,
                    pdf_path.name,
                    data.get("protocol_number"),
                    data.get("device_name"),
                    data.get("device_type"),
                    data.get("serial_number"),
                    data.get("mit_number"),
                    data.get("verification_method"),
                    data.get("manufacture_year"),
                    data.get("owner"),
                    data.get("verification_date"),
                    data.get("verifier"),
                    data.get("temperature"),
                    data.get("humidity"),
                    data.get("pressure"),
                    data.get("measurement_range"),
                    result.get("status"),
                    result.get("confidence"),
                    ocr_pages,
                    ocr_error,
                    text[:300].replace("\n", " "),
                ]
            )
        except Exception as e:
            print(f"ERROR processing {pdf_path.name}: {e}")
            ws.append([idx, pdf_path.name, f"ERROR: {e}"] + [""] * 19)

    auto_fit_columns(ws)
    wb.save(OUTPUT_PATH)
    print(f"Report saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
