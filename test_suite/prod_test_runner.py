"""Production-grade test runner for metroCheck extraction.

Uses the same code path as the backend:
  - protocol_scanner for OCR / text-layer extraction
  - protocol_extraction_service for regex + AI + vision fallback
  - ai_extraction_service for LLM fallback chain

Reports are written to reports/<timestamp>/ with:
  - summary.md          high-level results and per-field accuracy
  - errors.json         all mismatches and failure cases
  - errors.csv          same as JSON but spreadsheet-friendly
  - per_file.json       full extraction result per file
  - recommendations.md  actionable next steps generated from errors

Usage:
    source /tmp/metrocheck_test_venv/bin/activate
    OPENROUTER_API_KEY=sk-or-v1-... python test_suite/prod_test_runner.py

Environment:
    SAMPLE_FILE        path to arshin_matched_sample.json (default: ./arshin_matched_sample.json)
    OUTPUT_DIR         where to write reports (default: ./reports)
    PROTOCOLS_BASE     base path for protocol PDFs (default: /home/mflkee/SynologyDrive)
    OPENROUTER_API_KEY optional; if unset AI/vision fallbacks are skipped
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import multiprocessing
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Make backend app importable without running the full service
_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

# Minimal env so pydantic-settings does not fail on missing required vars
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost:5434/x")
os.environ.setdefault("REDIS_URL", "redis://localhost:6382")
os.environ.setdefault("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))
os.environ.setdefault("METROCHECK_LLM_CACHE", str(Path(__file__).resolve().parent / ".llm_cache"))

from app.services.protocol_extraction_service import (  # noqa: E402
    ProtocolExtractionService,
)
from app.services.protocol_scanner import (  # noqa: E402
    _extract_text_process,
    detect_file_type,
)

TEST_DIR = Path(os.path.dirname(__file__))
SAMPLE_FILE = Path(os.environ.get("SAMPLE_FILE", TEST_DIR / "arshin_matched_sample.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", TEST_DIR / "reports"))
PROTOCOLS_BASE = Path(os.environ.get("PROTOCOLS_BASE", "/home/mflkee/SynologyDrive"))


# ── ARSHIN comparison helpers (mirrors accuracy_test.py) ───────────────────


def _normalize_serial(s: str) -> str:
    return s.translate(str.maketrans("АВСЕКМНОРТХаеорсух", "ABCEKMHOPTXAEOPCyX"))


def _normalize_date(raw: str) -> str:
    """Normalize ARSHIN date string to YYYYMMDD."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y%m%d")
        except ValueError:
            pass
    return ""


def _stem(s: str) -> str:
    s = re.sub(r"\(.*?\)", "", s)
    words = s.replace(",", " ").split()
    normalized = []
    for w in words:
        w = w.lower().strip("«»\"'()[]")
        if len(w) <= 2:
            continue
        # Remove common Russian adjective/noun endings
        w = re.sub(r'(тел[иь]?|тель?)$', 'тел', w)
        w = re.sub(r'(ые|ии|ий|ый|ой|ая|яя|ое|ее|ие|ые|ого|его|ому|ему|ом|ем|ую|юю|ей|ий|ы|и|а|я|о|е|ь)$', '', w)
        if w:
            normalized.append(w)
    return " ".join(normalized[:6])


def compare_serial(extracted: Any, arshin_items: list[dict]) -> dict:
    proto = str(extracted or "").strip()
    if not arshin_items:
        return {"match": None, "extracted": proto, "arshin": "(no arshin data)"}
    arshin = (arshin_items[0].get("mi_number") or "").strip()
    proto_norm = _normalize_serial(proto).lower()
    arshin_norm = _normalize_serial(arshin).lower()
    return {"match": proto_norm == arshin_norm, "extracted": proto, "arshin": arshin}


def compare_mit(extracted: Any, arshin_items: list[dict]) -> dict:
    proto = str(extracted or "").strip()
    if not arshin_items:
        return {"match": None, "extracted": proto, "arshin": "(no arshin data)"}
    arshin_mits = {str(item.get("mit_number") or "").strip() for item in arshin_items}
    arshin_mits.discard("")
    match = bool(arshin_mits) and proto in arshin_mits
    return {
        "match": match,
        "extracted": proto,
        "arshin": ", ".join(sorted(arshin_mits)) if arshin_mits else "(empty)",
        "matched_event": next((item for item in arshin_items if str(item.get("mit_number") or "").strip() == proto), None),
    }


def compare_device_name(extracted: Any, arshin_items: list[dict]) -> dict:
    proto = (str(extracted or "")).split(";")[0].strip().lower()
    if not arshin_items:
        return {"match": None, "extracted": str(extracted or ""), "arshin": "(no arshin data)"}

    arshin_titles = [str(item.get("mit_title") or "").lower() for item in arshin_items]
    arshin_titles = [t for t in arshin_titles if t]

    proto_stem = _stem(proto)

    strict_match = False
    fuzzy_match = False
    best_title = ""
    for title in arshin_titles:
        if proto and (proto in title or title in proto):
            strict_match = True
            best_title = title
            break
        title_stem = _stem(title)
        if proto_stem and (proto_stem in title_stem or title_stem in proto_stem):
            fuzzy_match = True
            best_title = title

    return {
        "match": strict_match or fuzzy_match,
        "strict_match": strict_match,
        "extracted": str(extracted or ""),
        "arshin": best_title or (arshin_titles[0] if arshin_titles else "(empty)"),
    }


def compare_date(extracted: Any, arshin_items: list[dict]) -> dict:
    proto = str(extracted or "").strip()
    proto_clean = proto.replace("-", "").replace(".", "").replace("/", "")[:8]
    if not arshin_items:
        return {"match": None, "extracted": proto, "arshin": "(no arshin data)"}

    verification_dates = {_normalize_date(item.get("verification_date") or "") for item in arshin_items}
    verification_dates.discard("")

    # valid_date is usually "valid until", often next verification is one day after
    valid_dates = set()
    for item in arshin_items:
        raw = _normalize_date(item.get("valid_date") or "")
        if raw:
            valid_dates.add(raw)
            # Also consider ±1 day around valid_date because of timezone/human errors
            from datetime import timedelta
            dt = datetime.strptime(raw, "%Y%m%d")
            for delta in (-1, 0, 1):
                valid_dates.add((dt + timedelta(days=delta)).strftime("%Y%m%d"))

    matched_verification = next(
        (item for item in arshin_items if _normalize_date(item.get("verification_date") or "") == proto_clean),
        None,
    )
    matched_valid = next(
        (item for item in arshin_items
         if _normalize_date(item.get("valid_date") or "") in (proto_clean,)),
        None,
    )

    if proto_clean in verification_dates:
        status = "green"
        match = True
        note = "verification_date"
        matched_event = matched_verification
    elif proto_clean in valid_dates:
        status = "yellow"
        match = True  # soft match
        note = "valid_date (possible date confusion in protocol)"
        matched_event = matched_valid
    else:
        status = "red"
        match = False
        note = "no match"
        matched_event = None

    return {
        "match": match,
        "status": status,
        "note": note,
        "extracted": proto,
        "arshin": ", ".join(sorted(verification_dates)) if verification_dates else "(empty)",
        "valid_dates": ", ".join(sorted({_normalize_date(item.get('valid_date') or '') for item in arshin_items if item.get('valid_date')})) or "(empty)",
        "matched_event": matched_event,
    }


def compare_result(extracted: Any, arshin_items: list[dict]) -> dict:
    proto = str(extracted or "").lower().strip()
    if not arshin_items:
        return {"match": None, "extracted": proto, "arshin": "(no arshin data)"}
    arshin = "suitable" if arshin_items[0].get("applicability") else "unsuitable"
    return {"match": proto == arshin, "extracted": proto, "arshin": arshin}


def compare_owner(extracted: Any, arshin_items: list[dict]) -> dict:
    return {"match": None, "extracted": str(extracted or ""), "arshin": "(verification lab, not device owner)"}


def compare_verifier(extracted: Any, arshin_items: list[dict]) -> dict:
    return {"match": None, "extracted": str(extracted or ""), "arshin": "(not in public API)"}


COMPARATORS = {
    "serial_number": compare_serial,
    "mit_number": compare_mit,
    "device_name": compare_device_name,
    "verification_date": compare_date,
    "result": compare_result,
    "owner": compare_owner,
    "verifier": compare_verifier,
}

VALIDATABLE_FIELDS = {"serial_number", "mit_number", "device_name", "verification_date", "result"}


# ── ARSHIN API helpers with cache ──────────────────────────────────────────


_ARSHIN_CACHE_DIR = TEST_DIR / ".arshin_cache"


def _arshin_cache_key(serial: str) -> str:
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def _load_arshin_cache(serial: str) -> list[dict] | None:
    key = _arshin_cache_key(serial)
    cache_file = _ARSHIN_CACHE_DIR / f"{key}.json"
    try:
        if cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _save_arshin_cache(serial: str, items: list[dict]) -> None:
    try:
        _ARSHIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = _ARSHIN_CACHE_DIR / f"{_arshin_cache_key(serial)}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


async def fetch_arshin_records(serial: str) -> list[dict]:
    """Fetch all ARSHIN records for a serial number, using cache."""
    if not serial:
        return []

    cached = _load_arshin_cache(serial)
    if cached is not None:
        return cached

    import httpx

    arshin_url = "https://fgis.gost.ru/fundmetrology/eapi/vri"
    all_items: list[dict] = []
    start = 0
    rows_per_page = 20
    max_pages = 10

    async with httpx.AsyncClient(timeout=30.0) as client:
        for _ in range(max_pages):
            params = {
                "org_title": 'ООО "МКАИР"',
                "mi_number": serial,
                "start": start,
                "rows": rows_per_page,
            }
            try:
                resp = await client.get(arshin_url, params=params)
                resp.raise_for_status()
                data = resp.json()
                items = data.get("result", {}).get("items", [])
            except Exception:
                break

            if not items:
                break

            all_items.extend(items)
            if len(items) < rows_per_page:
                break
            start += rows_per_page

    _save_arshin_cache(serial, all_items)
    return all_items


# ── OCR helper using production scanner code ───────────────────────────────


def run_ocr(file_path: str, timeout: float = 180.0) -> dict[str, Any]:
    """Run the production OCR process in a separate process with timeout."""
    queue: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(target=_extract_text_process, args=(file_path, queue))
    proc.start()
    try:
        result = queue.get(timeout=timeout)
    except Exception:
        proc.terminate()
        result = {"error": f"timeout >{int(timeout)}s", "text": "", "pages": 0}
    finally:
        proc.join(timeout=5)
    return result


# ── Main runner ────────────────────────────────────────────────────────────


async def process_file(entry: dict, extractor: ProtocolExtractionService, idx: int, total: int) -> dict:
    fpath = entry["path"]
    fname = entry["filename"]
    print(f"  [{idx+1:2d}/{total}] {fname[:60]}", end=" ", flush=True)
    t0 = time.time()

    file_type = detect_file_type(fpath)
    ocr = run_ocr(fpath)
    text = ocr.get("text", "")
    ocr_err = ocr.get("error")

    if ocr_err or not text.strip():
        elapsed = time.time() - t0
        print(f"OCR_FAIL ({ocr_err or 'empty'}) {elapsed:.1f}s")
        return {
            "filename": fname,
            "year": entry["year"],
            "month": entry["month"],
            "path": fpath,
            "file_type": file_type,
            "ocr_text": text[:500],
            "ocr_pages": ocr.get("pages", 0),
            "ocr_error": ocr_err or "empty_text",
            "extracted": {},
            "confidence": 0.0,
            "status": "ocr_error",
            "comparisons": {},
            "accuracy": 0.0,
            "time": round(elapsed, 1),
        }

    extraction = await extractor.extract(text=text, file_name=fname, file_path=fpath)
    extracted = extraction.get("content", {})
    confidence = extraction.get("confidence", 0.0)
    serial = extracted.get("serial_number") or entry.get("serial", "")

    # Build ARSHIN ground truth: sample record + live API records
    arshin_items: list[dict] = []
    sample_arshin = entry.get("arshin")
    if isinstance(sample_arshin, dict):
        arshin_items.append(sample_arshin)
    elif isinstance(sample_arshin, list):
        arshin_items.extend(sample_arshin)

    arshin_status = "skipped"
    if serial:
        try:
            live_items = await fetch_arshin_records(serial)
            existing_ids = {item.get("vri_id") for item in arshin_items}
            for item in live_items:
                if item.get("vri_id") not in existing_ids:
                    arshin_items.append(item)
            arshin_status = f"ok ({len(arshin_items)} records)"
        except Exception as e:
            arshin_status = f"error: {e}"
    else:
        arshin_status = f"using sample ({len(arshin_items)} records)"

    # Compare with ARSHIN ground truth (all records for this serial)
    comparisons: dict[str, dict] = {}
    for field, cmp_fn in COMPARATORS.items():
        comparisons[field] = cmp_fn(extracted.get(field), arshin_items)

    # Find matched event for reporting
    matched_event = comparisons.get("verification_date", {}).get("matched_event") or comparisons.get("mit_number", {}).get("matched_event")

    match_count = sum(1 for c in comparisons.values() if c["match"] is True)
    total_valid = sum(1 for c in comparisons.values() if c["match"] is not None)
    accuracy = match_count / total_valid * 100 if total_valid else 0.0

    status = extraction.get("status", "manual_review")
    if confidence >= 0.6 and status != "success":
        status = "success"

    elapsed = time.time() - t0
    print(f"conf={confidence:.2f} acc={accuracy:.0f}% arshin={arshin_status} {elapsed:.1f}s")

    return {
        "filename": fname,
        "year": entry["year"],
        "month": entry["month"],
        "path": fpath,
        "file_type": file_type,
        "ocr_text": text[:500],
        "ocr_pages": ocr.get("pages", 0),
        "ocr_error": None,
        "extracted": extracted,
        "confidence": confidence,
        "status": status,
        "model_used": extraction.get("model_used"),
        "cost": extraction.get("cost", 0.0),
        "comparisons": comparisons,
        "accuracy": round(accuracy, 1),
        "time": round(elapsed, 1),
        "arshin_status": arshin_status,
        "arshin_events_count": len(arshin_items),
        "arshin_matched_event": matched_event,
    }


# ── Reporting ──────────────────────────────────────────────────────────────


def generate_reports(results: list[dict], output_dir: Path) -> dict[str, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = output_dir / timestamp
    report_dir.mkdir(parents=True, exist_ok=True)

    total = len(results)
    ocr_errors = [r for r in results if r.get("ocr_error")]
    manual_review = [r for r in results if r.get("status") == "manual_review" and not r.get("ocr_error")]
    successes = [r for r in results if r.get("status") == "success"]

    # Field-level stats
    field_stats: dict[str, list[bool]] = defaultdict(list)
    mismatches: list[dict] = []
    for r in results:
        for field, comp in r.get("comparisons", {}).items():
            if comp.get("match") is not None:
                field_stats[field].append(comp["match"])
            if comp.get("match") is False:
                mismatches.append({
                    "filename": r["filename"],
                    "year": r["year"],
                    "month": r["month"],
                    "path": r["path"],
                    "field": field,
                    "extracted": comp["extracted"],
                    "arshin": comp["arshin"],
                    "confidence": r.get("confidence"),
                })

    avg_conf = sum(r["confidence"] for r in results) / max(total, 1)
    avg_acc = sum(r["accuracy"] for r in results) / max(total, 1)

    # LLM usage stats
    llm_used = sum(1 for r in results if r.get("model_used"))
    total_cost = sum(r.get("cost", 0.0) for r in results)
    cache_dir = Path(os.environ.get("METROCHECK_LLM_CACHE", TEST_DIR / ".llm_cache"))
    cache_files = list(cache_dir.glob("*.json")) if cache_dir.exists() else []
    cache_size_mb = sum(f.stat().st_size for f in cache_files) / (1024 * 1024) if cache_files else 0.0

    # Date status breakdown
    date_statuses = {"green": 0, "yellow": 0, "red": 0}
    for r in results:
        status = r.get("comparisons", {}).get("verification_date", {}).get("status")
        if status in date_statuses:
            date_statuses[status] += 1

    # Save JSON artifacts
    per_file_path = report_dir / "per_file.json"
    with open(per_file_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    errors_path = report_dir / "errors.json"
    with open(errors_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_files": total,
            "ocr_errors": len(ocr_errors),
            "manual_review": len(manual_review),
            "mismatches": mismatches,
        }, f, ensure_ascii=False, indent=2, default=str)

    csv_path = report_dir / "errors.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "year", "month", "path", "field", "extracted", "arshin", "confidence"])
        writer.writeheader()
        writer.writerows(mismatches)

    # summary.md
    summary_path = report_dir / "summary.md"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# Отчёт по точности экстракции (production pipeline)\n\n")
        f.write(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Всего файлов:** {total}\n")
        f.write(f"**Успешно:** {len(successes)} ({len(successes)*100//max(total,1)}%)\n")
        f.write(f"**OCR-ошибки:** {len(ocr_errors)}\n")
        f.write(f"**На ручную проверку:** {len(manual_review)}\n")
        f.write(f"**Средний confidence:** {avg_conf:.2f}\n")
        f.write(f"**Средняя точность vs ARSHIN:** {avg_acc:.1f}%\n")
        f.write(f"**LLM-запросов:** {llm_used}\n")
        f.write(f"**Общая стоимость LLM:** ${total_cost:.4f}\n")
        f.write(f"**Кэш-файлов:** {len(cache_files)} ({cache_size_mb:.2f} MB)\n\n")

        f.write("## Точность по полям (только проверяемые в АРШИН)\n\n")
        f.write("| Поле | Совпадений | Всего | Точность |\n")
        f.write("|------|------------|-------|----------|\n")
        field_order = ["serial_number", "mit_number", "verification_date", "result", "device_name", "owner", "verifier"]
        for field in field_order:
            vals = field_stats.get(field, [])
            if vals:
                ok = sum(vals)
                acc = ok / len(vals) * 100
                f.write(f"| {field} | {ok} | {len(vals)} | {acc:.1f}% |\n")
            else:
                f.write(f"| {field} | — | — | информационно |\n")

        f.write("\n## Статусы сравнения дат\n\n")
        f.write("- Green: дата протокола = дата поверки в АРШИН\n")
        f.write("- Yellow: дата протокола = дата окончания срока действия (valid_date) — возможна путаница в протоколе\n")
        f.write("- Red: дата не совпала ни с одной датой в АРШИН\n\n")
        f.write("| Green | Yellow | Red |\n")
        f.write("|-------|--------|-----|\n")
        f.write(f"| {date_statuses['green']} | {date_statuses['yellow']} | {date_statuses['red']} |\n")

        if ocr_errors:
            f.write("\n## OCR-ошибки\n\n")
            for r in ocr_errors:
                f.write(f"- `{r['filename']}` — {r['ocr_error']}\n")

        if mismatches:
            f.write("\n## Топ ошибок по полям\n\n")
            by_field = defaultdict(list)
            for m in mismatches:
                by_field[m["field"]].append(m)
            for field in field_order:
                items = by_field.get(field, [])
                if not items:
                    continue
                f.write(f"\n### {field} ({len(items)} ошибок)\n\n")
                f.write("| Файл | Извлечено | АРШИН |\n")
                f.write("|------|-----------|-------|\n")
                for m in items[:10]:
                    ext = str(m["extracted"]).replace("\n", " ")[:60]
                    ars = str(m["arshin"]).replace("\n", " ")[:60]
                    f.write(f"| `{m['filename'][:45]}` | `{ext}` | `{ars}` |\n")

    # recommendations.md
    recommendations = _build_recommendations(results, mismatches, field_stats, ocr_errors)
    rec_path = report_dir / "recommendations.md"
    with open(rec_path, "w", encoding="utf-8") as f:
        f.write(recommendations)

    return {
        "dir": report_dir,
        "summary": summary_path,
        "errors_json": errors_path,
        "errors_csv": csv_path,
        "per_file": per_file_path,
        "recommendations": rec_path,
    }


def _build_recommendations(
    results: list[dict],
    mismatches: list[dict],
    field_stats: dict[str, list[bool]],
    ocr_errors: list[dict],
) -> str:
    lines = ["# Рекомендации по улучшению\n"]

    # OCR
    if ocr_errors:
        lines.append("## OCR и чтение файлов\n")
        lines.append(f"- {len(ocr_errors)} файлов не удалось распознать. Проверить:\n")
        lines.append("  - корректность magic bytes;\n")
        lines.append("  - доступность tesseract-ocr и tesseract-ocr-osd;\n")
        lines.append("  - качество исходных сканов (DPI, разрешение).\n")
        lines.append("- Для плохих сканов обязателен vision fallback (уже есть в проде).\n\n")

    # Per-field recommendations
    lines.append("## Точность по полям\n")
    for field, vals in field_stats.items():
        if not vals:
            continue
        acc = sum(vals) / len(vals) * 100
        if acc >= 95:
            lines.append(f"- **{field}**: {acc:.1f}% — оставить как есть.\n")
        elif acc >= 80:
            lines.append(f"- **{field}**: {acc:.1f}% — можно доработать редкие кейсы, но не критично.\n")
        else:
            lines.append(f"- **{field}**: {acc:.1f}% — **требует внимания**.\n")

    # Specific device_name advice
    dev_errors = [m for m in mismatches if m["field"] == "device_name"]
    if dev_errors:
        lines.append("\n## device_name — конкретные проблемы\n")
        glued = [m for m in dev_errors if re.search(r"[а-яё][A-ZА-Я0-9]", str(m["extracted"]))]
        junk = [m for m in dev_errors if re.search(r"нормативн|документ|методик|поверк", str(m["extracted"]), re.IGNORECASE)]
        if glued:
            lines.append(f"- **Склейка слов** ({len(glued)} случаев): нужен постпроцессинг OCR/текстового слоя.\n")
            lines.append("  Примеры:\n")
            for m in glued[:3]:
                lines.append(f"    - `{m['filename']}`: `{m['extracted']}`\n")
        if junk:
            lines.append(f"- **Мусор вместо названия** ({len(junk)} случаев): regex уходит в соседнюю строку.\n")
            lines.append("  Примеры:\n")
            for m in junk[:3]:
                lines.append(f"    - `{m['filename']}`: `{m['extracted']}`\n")
        lines.append("- Рекомендуется добавить стемминг мн./ед. числа и чёрный список стартовых слов.\n")

    # Date/MIT mismatch advice
    date_errors = [m for m in mismatches if m["field"] == "verification_date"]
    if date_errors:
        lines.append("\n## verification_date\n")
        lines.append(f"- {len(date_errors)} расхождений. Часто это разные события поверки одного серийника.\n")
        lines.append("- Добавить логику: если дата в PDF ≠ последняя дата в АРШИН, но обе даты корректны — это **не ошибка экстракции**, а предупреждение.\n")

    # LLM fallback advice
    llm_used = sum(1 for r in results if r.get("model_used"))
    low_conf = [r for r in results if r.get("confidence", 0) < 0.5 and not r.get("ocr_error")]
    lines.append("\n## Когда обращаться к LLM\n")
    lines.append(f"- LLM/vision использовался в {llm_used} файлах.\n")
    lines.append(f"- {len(low_conf)} файлов имеют confidence < 0.5 после всех fallback.\n")
    if low_conf:
        lines.append("- Для этих файлов рекомендуется:\n")
        lines.append("  1. Проверить качество OCR/исходника.\n")
        lines.append("  2. Если OCR нормальный — увеличить максимальное число токенов/попыток LLM.\n")
        lines.append("  3. Если LLM всё равно не справляется — отправлять на ручную проверку.\n")

    lines.append("\n## Общие следующие шаги\n")
    lines.append("1. Провести ручную верификацию 5–10 кейсов с расхождениями дат/MIT.\n")
    lines.append("2. Перенести исправления device_name из анализа в production `_extract_device_name`.\n")
    lines.append("3. Добавить метрику 'extraction method per field' (regex / OCR / LLM / vision).\n")
    lines.append("4. Настроить алёртинг, если доля manual_review превышает 5%.\n")

    return "".join(lines)


# ── Entry point ────────────────────────────────────────────────────────────


async def main():
    with open(SAMPLE_FILE, encoding="utf-8") as f:
        sample = json.load(f)

    print("=" * 70)
    print("metroCheck Production Pipeline Test")
    print(f"Sample: {len(sample)} files")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 70)

    extractor = ProtocolExtractionService()
    results: list[dict] = []

    for i, entry in enumerate(sample):
        r = await process_file(entry, extractor, i, len(sample))
        results.append(r)

    print("\n" + "=" * 70)
    print("Generating reports...")
    paths = generate_reports(results, OUTPUT_DIR)
    print("=" * 70)
    print(f"Reports saved to: {paths['dir']}")
    print(f"  summary:          {paths['summary']}")
    print(f"  errors.json:      {paths['errors_json']}")
    print(f"  errors.csv:       {paths['errors_csv']}")
    print(f"  per_file.json:    {paths['per_file']}")
    print(f"  recommendations:  {paths['recommendations']}")


if __name__ == "__main__":
    asyncio.run(main())
