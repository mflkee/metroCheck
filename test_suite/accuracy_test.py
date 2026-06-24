"""Accuracy test on ARSHIN-matched protocol sample.

Reads pre-built sample from arshin_matched_sample.json,
runs OCR + regex + AI extraction, compares with ARSHIN ground truth.

Usage:
    source /tmp/metrocheck_test_venv/bin/activate
    OPENROUTER_API_KEY=sk-or-v1-... python test_suite/accuracy_test.py
"""

import asyncio
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

TEST_DIR = Path(os.path.dirname(__file__))
SAMPLE_FILE = TEST_DIR / "arshin_matched_sample.json"
OUTPUT_DIR = TEST_DIR / "reports"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Imports from run_test.py ────────────────────────────────────────────────
sys.path.insert(0, str(TEST_DIR))
from run_test import (
    run_ocr, extract_all, calculate_confidence,
    _normalize_serial,
)
from run_test import _match_first, MONTH_MAP  # noqa: F401 — used by extractors


# ── Per-field comparison functions ─────────────────────────────────────────

def compare_serial(extracted: Any, arshin_item: dict) -> dict:
    proto = str(extracted or "").strip()
    arshin = (arshin_item.get("mi_number") or "").strip()
    proto_norm = _normalize_serial(proto).lower()
    arshin_norm = _normalize_serial(arshin).lower()
    return {"match": proto_norm == arshin_norm, "extracted": proto, "arshin": arshin}


def compare_mit(extracted: Any, arshin_item: dict) -> dict:
    proto = str(extracted or "").strip()
    arshin = (arshin_item.get("mit_number") or "").strip()
    return {"match": proto == arshin, "extracted": proto, "arshin": arshin}


def compare_device_name(extracted: Any, arshin_item: dict) -> dict:
    proto = (str(extracted or "")).split(";")[0].strip().lower()
    arshin = (arshin_item.get("mit_title") or "").lower()
    
    # Fuzzy: normalize plural/singular, remove model suffixes
    def stem(s: str) -> str:
        s = re.sub(r'\(.*?\)', '', s)
        words = s.replace(',', ' ').split()
        normalized = []
        for w in words:
            w = w.lower().strip('«»\"\'()[]')
            if len(w) <= 2:
                continue
            # Remove common Russian adjective/noun endings
            w = re.sub(r'(тел[иь]?|тель?)$', 'тел', w)
            w = re.sub(r'(ые|ии|ий|ый|ой|ая|яя|ое|ее|ие|ые|ого|его|ому|ему|ом|ем|ую|юю|ей|ий|ы|и|а|я|о|е|ь)$', '', w)
            if w:
                normalized.append(w)
        return ' '.join(normalized[:6])
    
    proto_stem = stem(proto)
    arshin_stem = stem(arshin)
    
    strict_match = bool(proto) and (proto in arshin or arshin in proto)
    fuzzy_match = bool(proto_stem) and (proto_stem in arshin_stem or arshin_stem in proto_stem)
    
    return {
        "match": fuzzy_match,  # primary: fuzzy comparison
        "strict_match": strict_match,
        "extracted": str(extracted or ""),
        "arshin": arshin_item.get("mit_title", ""),
    }


def compare_date(extracted: Any, arshin_item: dict) -> dict:
    proto = str(extracted or "").strip()
    arshin_raw = arshin_item.get("verification_date") or ""
    # Normalize both to YYYYMMDD
    proto_clean = proto.replace("-", "").replace(".", "").replace("/", "")[:8]
    arshin_clean = ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            arshin_clean = datetime.strptime(arshin_raw, fmt).strftime("%Y%m%d")
            break
        except ValueError:
            pass
    match = proto_clean == arshin_clean if proto_clean and arshin_clean else False
    return {"match": match, "extracted": proto, "arshin": arshin_raw}


def compare_result(extracted: Any, arshin_item: dict) -> dict:
    proto = str(extracted or "").lower().strip()
    arshin = "suitable" if arshin_item.get("applicability") else "unsuitable"
    return {"match": proto == arshin, "extracted": str(extracted or ""), "arshin": arshin}


def compare_owner(extracted: Any, arshin_item: dict) -> dict:
    # ARSHIN shows verification LAB (ООО МКАИР), protocol shows DEVICE owner.
    # These are different entities — not comparable. Skip comparison.
    return {"match": None, "extracted": str(extracted or ""), "arshin": "(verification lab, not device owner)"}


def compare_verifier(extracted: Any, arshin_item: dict) -> dict:
    return {"match": None, "extracted": str(extracted or ""), "arshin": "(not in public API)"}


# Recalculated: only compare fields that ARSHIN actually validates
# serial_number, mit_number, device_name (fuzzy), verification_date, result
VALIDATABLE_FIELDS = {"serial_number", "mit_number", "device_name", "verification_date", "result"}


# ── Test runner ────────────────────────────────────────────────────────────

async def main():
    with open(SAMPLE_FILE) as f:
        sample = json.load(f)

    ai_label = "+AI" if OPENROUTER_API_KEY else "(regex-only)"
    print("=" * 70)
    print(f"metroCheck Accuracy Test {ai_label}")
    print(f"Sample: {len(sample)} ARSHIN-matched files")
    print("=" * 70)

    # Comparison map: field -> compare function
    COMPARATORS = {
        "serial_number": compare_serial,
        "mit_number": compare_mit,
        "device_name": compare_device_name,
        "verification_date": compare_date,
        "result": compare_result,
        "owner": compare_owner,      # informational only
        "verifier": compare_verifier, # informational only
    }

    results = []
    field_stats: dict[str, list[bool | None]] = defaultdict(list)
    mismatches: list[dict] = []

    for i, entry in enumerate(sample):
        fpath = entry["path"]
        fname = entry["filename"]
        arshin = entry["arshin"]
        print(f"\n[{i+1:2d}/{len(sample)}] {fname[:65]}", end=" ", flush=True)
        t0 = time.time()

        # OCR
        ocr = run_ocr(fpath)
        text = ocr.get("text", "")
        ocr_err = ocr.get("error")
        if ocr_err:
            print(f"OCR ERROR: {ocr_err}")
            continue

        # Extraction
        extracted = extract_all(text, fname, OPENROUTER_API_KEY)
        conf = calculate_confidence(extracted)

        elapsed = time.time() - t0

        # Per-field comparison
        comparisons = {}
        for field, cmp_fn in COMPARATORS.items():
            cmp = cmp_fn(extracted.get(field), arshin)
            comparisons[field] = cmp
            if cmp["match"] is not None:
                field_stats[field].append(cmp["match"])

        # Count matches
        match_count = sum(1 for c in comparisons.values() if c["match"] is True)
        total_valid = sum(1 for c in comparisons.values() if c["match"] is not None)
        acc = match_count / total_valid * 100 if total_valid else 0

        # Status line — show only validatable fields
        detail = " ".join(
            f"{'✓' if comparisons[f].get('match', None) is True else '✗' if comparisons[f].get('match') is False else '?'}{f[:4]}"
            for f in ["serial_number", "mit_number", "device_name", "verification_date", "result"]
        )
        print(f"conf={conf:.2f} acc={acc:.0f}% [{detail}] in {elapsed:.1f}s")

        # Log failures for analysis
        for field, cmp in comparisons.items():
            if cmp["match"] is False:
                mismatches.append({
                    "file": fname, "field": field,
                    "extracted": cmp["extracted"], "arshin": cmp["arshin"],
                })

        results.append({
            "filename": fname, "year": entry["year"], "month": entry["month"],
            "serial": entry["serial"], "device_hint": entry["device_hint"],
            "confidence": round(conf, 2),
            "accuracy": round(acc, 1),
            "extracted": extracted,
            "comparisons": comparisons,
            "ocr_error": ocr_err,
            "time": round(elapsed, 1),
        })

    # ── Report ────────────────────────────────────────────────────────

    print("\n" + "=" * 70)
    print("ACCURACY REPORT")
    print("=" * 70)
    print(f"Files tested:      {len(results)}")
    print(f"Avg confidence:    {sum(r['confidence'] for r in results)/len(results):.2f}")
    print(f"Avg accuracy:      {sum(r['accuracy'] for r in results)/len(results):.1f}%")
    print()

    # Per-field accuracy
    print(f"{'Field':<22s} {'Matches':>8s} {'Accuracy':>10s}  Bar")
    print("-" * 70)
    field_order = ["serial_number", "mit_number", "verification_date", "result",
                   "device_name", "owner", "verifier"]
    for field in field_order:
        vals = field_stats.get(field, [])
        if vals:
            ok = sum(vals)
            acc = ok / len(vals) * 100
            bar = "█" * int(acc / 5) + "░" * (20 - int(acc / 5))
            print(f"  {field:<22s} {ok:3d}/{len(vals):<3d} {acc:8.1f}%  [{bar}]")
        else:
            print(f"  {field:<22s} {'(info only)':>16s}")

    # Device name breakdown
    dev_fuzzy = sum(1 for r in results if r["comparisons"].get("device_name", {}).get("match"))
    dev_strict = sum(1 for r in results if r["comparisons"].get("device_name", {}).get("strict_match"))
    print(f"\n  device_name: {dev_fuzzy}/{len(results)} fuzzy, {dev_strict}/{len(results)} strict")

    # Top mismatches by field
    print(f"\n── Top mismatches ({len(mismatches)} total) ──\n")
    by_field = defaultdict(list)
    for mm in mismatches:
        by_field[mm["field"]].append(mm)

    for field in field_order:
        items = by_field.get(field, [])
        if not items:
            continue
        print(f"  {field} ({len(items)} errors):")
        for m in items[:5]:
            ext = str(m["extracted"])[:55]
            ars = str(m["arshin"])[:55]
            print(f"    ext: {ext}")
            print(f"    ars: {ars}")
            print()

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = OUTPUT_DIR / f"accuracy_test_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "mismatches": mismatches}, f, ensure_ascii=False, indent=2, default=str)
    print(f"Report: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
