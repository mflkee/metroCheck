"""Test pipeline for protocol extraction accuracy.

Samples diverse protocols from SynologyDrive, runs full extraction pipeline,
and compares results with ARSHIN API ground truth.

Usage (inside Docker container):
    PROTOCOLS_PATH=/protocols \
    OUTPUT_DIR=/reports \
    OPENROUTER_API_KEY=sk-or-v1-... \
    python test_suite/sample_and_test.py

Or on host (requires Tesseract + poppler + Python deps):
    PROTOCOLS_PATH=/home/mflkee/SynologyDrive \
    OUTPUT_DIR=./test_suite/reports \
    python test_suite/sample_and_test.py

Phases:
    1. Sample — select diverse PDFs across years/months
    2. Copy — copy sampled files to test dir (never modify originals)
    3. Extract — OCR + regex + AI + vision fallback
    4. Validate — compare with ARSHIN API data
    5. Report — generate Excel + console report
"""

import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROTOCOLS_PATH = Path(os.environ.get("PROTOCOLS_PATH", "/home/mflkee/SynologyDrive"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", f"{os.path.dirname(__file__)}/reports"))
MAX_SAMPLE = int(os.environ.get("MAX_SAMPLE", "60"))  # Max files to test
SAMPLE_PER_GROUP = int(os.environ.get("SAMPLE_PER_GROUP", "2"))  # Files per year/month
SKIP_AI = os.environ.get("SKIP_AI", "").lower() in ("1", "true", "yes")

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Phase 1: Sampling ──────────────────────────────────────────────────────

def sample_protocols(
    base_path: Path,
    max_total: int = MAX_SAMPLE,
    per_group: int = SAMPLE_PER_GROUP,
    random_seed: int = 42,
) -> list[dict[str, Any]]:
    """Select diverse protocol PDFs across years and months.

    Does NOT modify or move any files — only records paths.

    Returns list of {year, month, path, size, filename}.
    """
    random.seed(random_seed)

    # Collect all protocol files grouped by (year, month)
    groups: dict[tuple[int, int], list[Path]] = defaultdict(list)

    for year_dir in sorted(base_path.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue
        if year < 2022 or year > 2026:
            continue

        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            try:
                month = int(month_dir.name)
            except ValueError:
                continue
            if month < 1 or month > 12:
                continue

            pdfs = list(month_dir.glob("*.pdf")) + list(month_dir.glob("*.PDF"))
            if pdfs:
                groups[(year, month)] = pdfs

    print(f"Found {len(groups)} year/month groups with protocols")
    total_files = sum(len(v) for v in groups.values())
    print(f"Total protocol files available: {total_files}")

    # Sample per group
    sample_pool: list[Path] = []
    for (year, month), files in sorted(groups.items()):
        n = min(per_group, len(files))
        chosen = random.sample(files, n)
        sample_pool.extend(chosen)

    # If exceeds max, randomly downsample
    if len(sample_pool) > max_total:
        sample_pool = random.sample(sample_pool, max_total)

    # Shuffle for variety in processing
    random.shuffle(sample_pool)

    result = []
    for path in sample_pool:
        rel = path.relative_to(base_path)
        parts = rel.parts  # e.g., ("2025", "03", "file.pdf")
        year = int(parts[0])
        month = int(parts[1])
        result.append({
            "year": year,
            "month": month,
            "path": str(path),
            "filename": path.name,
            "size": path.stat().st_size,
        })

    print(f"Sampled {len(result)} files across {len(set((r['year'], r['month']) for r in result))} groups")
    return result


# ── Phase 3: Extraction ────────────────────────────────────────────────────

def extract_protocol(file_path: str, filename: str) -> dict[str, Any]:
    """Run full extraction pipeline on a single protocol file.

    Uses OCR → regex → AI text → vision fallback.
    """
    # Import inside container
    sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

    from app.services.protocol_scanner import _extract_text_process
    import multiprocessing

    # Phase 3a: OCR
    queue: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(target=_extract_text_process, args=(file_path, queue))
    proc.start()
    try:
        ocr_result = queue.get(timeout=120)
    except Exception:
        proc.terminate()
        ocr_result = {"error": "OCR timeout", "text": "", "pages": 0}
    finally:
        proc.join(timeout=5)

    text = ocr_result.get("text", "")[:2000]

    # Phase 3b: Regex + AI extraction
    from app.services.protocol_extraction_service import get_protocol_extraction_service

    service = get_protocol_extraction_service()
    extraction = asyncio.run(service.extract(
        text=text,
        file_name=filename,
        file_path=file_path,
    ))

    return {
        "file_path": file_path,
        "filename": filename,
        "ocr_text": text[:500],
        "ocr_pages": ocr_result.get("pages", 0),
        "ocr_error": ocr_result.get("error"),
        "extracted": extraction.get("content", {}),
        "confidence": extraction.get("confidence", 0),
        "status": extraction.get("status"),
        "cost": extraction.get("cost", 0),
        "model_used": extraction.get("model_used"),
    }


# ── Phase 4: ARSHIN Validation ─────────────────────────────────────────────

async def validate_via_arshin(extracted: dict[str, Any]) -> dict[str, Any]:
    """Compare extraction result with ARSHIN API ground truth.

    Queries ARSHIN by serial number and compares fields.
    """
    serial = (extracted.get("extracted", {}) or {}).get("serial_number")
    if not serial:
        return {"status": "no_serial", "comparisons": {}}

    # Query ARSHIN public API
    import httpx
    settings_path = str(Path(__file__).parent.parent / "backend")
    if settings_path not in sys.path:
        sys.path.insert(0, settings_path)

    from app.core.config import settings

    arshin_url = f"{settings.ARSHIN_BASE_URL}/vri"
    params = {
        "org_title": 'ООО "МКАИР"',
        "mi_number": serial,
        "rows": 5,
    }

    arshin_data = None
    comparisons = {}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(arshin_url, params=params)
            resp.raise_for_status()
            result = resp.json()
            items = result.get("result", {}).get("items", [])
            if items:
                arshin_data = items[0]
    except Exception as e:
        return {"status": f"arshin_error_{e}", "comparisons": {}, "serial": serial}

    if not arshin_data:
        return {"status": "no_arshin_match", "comparisons": {}, "serial": serial}

    proto = extracted.get("extracted", {}) or {}

    # Compare fields
    field_map = {
        "serial_number": arshin_data.get("mi_number", "").strip(),
        "mit_number": arshin_data.get("mit_number", ""),
        "device_name": arshin_data.get("mit_title", ""),
        "verification_date": arshin_data.get("verification_date", ""),
        "result": "suitable" if arshin_data.get("applicability") else "unsuitable",
        "owner": arshin_data.get("org_title", ""),
    }

    for field, arshin_value in field_map.items():
        proto_value = proto.get(field)
        if proto_value is None:
            comparisons[field] = {"match": False, "reason": "not_extracted", "arshin": str(arshin_value)}
            continue

        # Normalize and compare
        proto_str = str(proto_value).strip()
        arshin_str = str(arshin_value).strip()

        if field == "serial_number":
            # Normalize homoglyphs
            proto_str = _normalize_serial(proto_str)
            arshin_str = _normalize_serial(arshin_str)
            is_match = proto_str.lower() == arshin_str.lower()
        elif field == "verification_date":
            # Compare YYYY-MM-DD parts, ignoring formatting
            proto_clean = proto_str.replace("-", "").replace(".", "").replace("/", "")[:8]
            arshin_clean = _parse_arshin_date(arshin_str)
            is_match = proto_clean == arshin_clean
        elif field == "device_name":
            # Substring match (ARSHIN names are often longer)
            is_match = proto_str.lower() in arshin_str.lower() or arshin_str.lower() in proto_str.lower()
        elif field == "result":
            is_match = proto_str.lower() == arshin_str.lower()
        elif field == "owner":
            # Normalize quotes and whitespace
            proto_clean = proto_str.replace('"', "").replace("«", "").replace("»", "").lower()
            arshin_clean = arshin_str.replace('"', "").replace("«", "").replace("»", "").lower()
            is_match = proto_clean[:20] in arshin_clean or arshin_clean[:20] in proto_clean
        else:
            is_match = proto_str.lower() == arshin_str.lower()

        comparisons[field] = {
            "match": is_match,
            "extracted": proto_str,
            "arshin": arshin_str,
        }

    return {
        "status": "ok",
        "serial": serial,
        "vri_id": arshin_data.get("vri_id"),
        "comparisons": comparisons,
    }


def _normalize_serial(s: str) -> str:
    """Normalize cyrillic homoglyphs in serial numbers."""
    mapping = str.maketrans("АВСЕКМНОРТХаеорсух", "ABCEKMHOPTXAEOPCyX")
    return s.translate(mapping)


def _parse_arshin_date(date_str: str) -> str:
    """Convert ARSHIN date format to YYYYMMDD."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y%m%d")
        except ValueError:
            pass
    return date_str.replace(".", "").replace("-", "")[:8]


# ── Phase 5: Report Generation ─────────────────────────────────────────────

def generate_report(results: list[dict[str, Any]], output_dir: Path) -> str:
    """Generate Excel report and console summary."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Console report
    total = len(results)
    success = sum(1 for r in results if r.get("status") == "success")
    manual = sum(1 for r in results if r.get("status") == "manual_review")
    ocr_errors = sum(1 for r in results if r.get("ocr_error"))
    ai_cost = sum(r.get("cost", 0) for r in results)

    # Field accuracy (from validation)
    field_matches: defaultdict[str, list[bool]] = defaultdict(list)
    validated = 0
    for r in results:
        comps = r.get("validation", {}).get("comparisons", {})
        if comps:
            validated += 1
            for field, comp in comps.items():
                field_matches[field].append(comp.get("match", False))

    print("\n" + "=" * 70)
    print("TEST PIPELINE REPORT")
    print("=" * 70)
    print(f"Total files tested:      {total}")
    print(f"Success (conf >= 0.4):   {success} ({success*100//max(total,1)}%)")
    print(f"Manual review:           {manual}")
    print(f"OCR errors:              {ocr_errors}")
    print(f"AI cost:                 ${ai_cost:.4f}")
    print(f"ARSHIN validated:        {validated}")
    print()
    print("Field accuracy vs ARSHIN:")
    for field in sorted(field_matches.keys()):
        matches = field_matches[field]
        acc = sum(matches) / len(matches) * 100
        bar = "█" * int(acc / 5) + "░" * (20 - int(acc / 5))
        print(f"  {field:<22s} [{bar}] {acc:5.1f}% ({sum(matches)}/{len(matches)})")
    print("=" * 70)

    # Excel report
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Extraction Test"

        # Headers
        headers = [
            "#", "File", "Year", "Month", "Status", "Confidence",
            "Protocol #", "Device Name", "Type", "Serial #", "MIT #",
            "Year Mfg", "Owner", "Verif Date", "Verifier",
            "Temp", "Hum", "Pressure", "Range", "Result", "Method",
            "Model Used", "Cost", "OCR Error", "OCR Text (300ch)",
        ]
        for i, h in enumerate(headers, 1):
            cell = ws.cell(1, i, h)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # Green/red fills for status
        green = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

        for idx, r in enumerate(results, 1):
            data = r.get("extracted", {}) or {}
            row = [
                idx,
                r.get("filename", ""),
                r.get("year", ""),
                r.get("month", ""),
                r.get("status", ""),
                r.get("confidence", 0),
                data.get("protocol_number"),
                data.get("device_name"),
                data.get("device_type"),
                data.get("serial_number"),
                data.get("mit_number"),
                data.get("manufacture_year"),
                data.get("owner"),
                data.get("verification_date"),
                data.get("verifier"),
                data.get("temperature"),
                data.get("humidity"),
                data.get("pressure"),
                data.get("measurement_range"),
                data.get("result"),
                data.get("verification_method"),
                r.get("model_used", ""),
                r.get("cost", 0),
                r.get("ocr_error", ""),
                (r.get("ocr_text", "") or "")[:300],
            ]
            for col, val in enumerate(row, 1):
                cell = ws.cell(idx + 1, col, val)
                if col == 5:  # Status column
                    if val == "success":
                        cell.fill = green
                    elif val == "manual_review":
                        cell.fill = red

        # Validation sheet
        if validated > 0:
            ws2 = wb.create_sheet("ARSHIN Validation")
            val_headers = ["File", "Serial", "Field", "Match", "Extracted", "ARSHIN"]
            for i, h in enumerate(val_headers, 1):
                ws2.cell(1, i, h).font = Font(bold=True)

            row = 2
            for r in results:
                comps = r.get("validation", {}).get("comparisons", {})
                if not comps:
                    continue
                for field, comp in comps.items():
                    ws2.cell(row, 1, r.get("filename", ""))
                    ws2.cell(row, 2, r.get("validation", {}).get("serial", ""))
                    ws2.cell(row, 3, field)
                    ws2.cell(row, 4, "✓" if comp.get("match") else "✗")
                    ws2.cell(row, 5, str(comp.get("extracted", ""))[:100])
                    ws2.cell(row, 6, str(comp.get("arshin", ""))[:100])
                    row += 1

        report_path = output_dir / f"extraction_test_{timestamp}.xlsx"
        wb.save(report_path)
        print(f"\nExcel report: {report_path}")

        # JSON report for programmatic analysis
        json_path = output_dir / f"extraction_test_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"JSON report: {json_path}")

        return str(report_path)
    except ImportError:
        print("\nNo openpyxl available — skipping Excel report")
        return ""


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    print("=" * 70)
    print("metroCheck Protocol Extraction Test Pipeline")
    print("=" * 70)
    print(f"Source: {PROTOCOLS_PATH}")
    print(f"Output: {OUTPUT_DIR}")
    print(f"Max sample: {MAX_SAMPLE}")
    print(f"AI enabled: {not SKIP_AI}")
    print()

    # Phase 1: Sample
    print("── Phase 1: Sampling protocols ──")
    samples = sample_protocols(PROTOCOLS_PATH)
    if not samples:
        print("No protocols found!")
        return

    # Save sample list
    sample_json = OUTPUT_DIR / "sample_list.json"
    with open(sample_json, "w") as f:
        json.dump(samples, f, ensure_ascii=False, indent=2)

    # Phase 3: Extract
    print(f"\n── Phase 2: Extracting {len(samples)} protocols ──")
    results = []
    for i, sample in enumerate(samples):
        fpath = sample["path"]
        fname = sample["filename"]
        print(f"  [{i+1}/{len(samples)}] {fname[:60]}...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = extract_protocol(fpath, fname)
            result["year"] = sample["year"]
            result["month"] = sample["month"]
            elapsed = time.time() - t0
            conf = result.get("confidence", 0)
            status = result.get("status", "?")
            print(f"{status} conf={conf:.2f} in {elapsed:.1f}s")
            results.append(result)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "year": sample["year"],
                "month": sample["month"],
                "filename": fname,
                "file_path": fpath,
                "status": "error",
                "error": str(e),
                "extracted": {},
            })

    # Phase 4: Validate via ARSHIN
    print(f"\n── Phase 3: Validating via ARSHIN API ──")
    for i, result in enumerate(results):
        if result.get("status") == "error":
            continue
        serial = (result.get("extracted", {}) or {}).get("serial_number")
        print(f"  [{i+1}/{len(results)}] {result['filename'][:50]}... serial={serial}", end=" ", flush=True)
        try:
            validation = await validate_via_arshin(result)
            result["validation"] = validation
            print(f"→ {validation.get('status')}")
        except Exception as e:
            print(f"ERROR: {e}")
            result["validation"] = {"status": f"error_{e}", "comparisons": {}}

    # Phase 5: Report
    print(f"\n── Phase 4: Generating report ──")
    generate_report(results, OUTPUT_DIR)

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
