"""Test pipeline for protocol extraction accuracy — standalone, no DB deps.

Samples diverse protocols from SynologyDrive, runs full extraction pipeline,
and compares results with ARSHIN API ground truth.

Usage:
    source /tmp/metrocheck_test_venv/bin/activate
    PROTOCOLS_PATH=/home/mflkee/SynologyDrive MAX_SAMPLE=15 \
        python test_suite/run_test.py
"""

import asyncio
import json
import multiprocessing
import os
import random
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

PROTOCOLS_PATH = Path(os.environ.get("PROTOCOLS_PATH", "/home/mflkee/SynologyDrive"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", f"{os.path.dirname(__file__)}/reports"))
MAX_SAMPLE = int(os.environ.get("MAX_SAMPLE", "60"))
SAMPLE_PER_GROUP = int(os.environ.get("SAMPLE_PER_GROUP", "2"))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Magic bytes detection ──────────────────────────────────────────────────

_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    "application/pdf": [b"%PDF-"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
}


def detect_file_type(file_path: str) -> str | None:
    try:
        with open(file_path, "rb") as f:
            header = f.read(12)
    except OSError:
        return None
    for mime, sigs in _MAGIC_SIGNATURES.items():
        for sig in sigs:
            if header.startswith(sig):
                return mime
    ext = os.path.splitext(file_path)[1].lower()
    return {".pdf": "application/pdf", ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg", ".png": "image/png"}.get(ext)


# ── OCR (multiprocessing) ──────────────────────────────────────────────────

def _ocr_process(file_path: str, queue: Any) -> None:
    import pdfplumber
    import pytesseract
    from PIL import Image, ImageFilter, ImageOps
    from pdf2image import convert_from_path

    try:
        ftype = detect_file_type(file_path)
        if ftype and ftype.startswith("image/"):
            with Image.open(file_path) as img:
                if img.mode != "L":
                    img = img.convert("L")
                img = ImageOps.autocontrast(img, cutoff=2)
                img = img.filter(ImageFilter.SHARPEN)
                text = pytesseract.image_to_string(img, lang="rus+eng")
            pages = 1
        else:
            parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        parts.append(t)
            text = "\n".join(parts)
            pages = len(parts)
            if not text.strip():
                images = convert_from_path(file_path)
                pages = len(images)
                ocr_parts = []
                for img in images:
                    if img.mode != "L":
                        img = img.convert("L")
                    img = ImageOps.autocontrast(img, cutoff=2)
                    img = img.filter(ImageFilter.SHARPEN)
                    ocr_parts.append(pytesseract.image_to_string(img, lang="rus+eng"))
                text = "\n".join(ocr_parts)
        queue.put({"text": text, "pages": pages, "error": None})
    except Exception as e:
        queue.put({"error": str(e), "text": "", "pages": 0})


def run_ocr(file_path: str, timeout: float = 120.0) -> dict[str, Any]:
    queue = multiprocessing.Queue()
    proc = multiprocessing.Process(target=_ocr_process, args=(file_path, queue))
    proc.start()
    try:
        result = queue.get(timeout=timeout)
    except Exception:
        proc.terminate()
        result = {"error": f"timeout >{int(timeout)}s", "text": "", "pages": 0}
    finally:
        proc.join(timeout=5)
    return result


# ── Regex Extraction (standalone, no DB) ───────────────────────────────────

MONTH_MAP = {
    'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
    'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
    'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
}


def _match_first(text: str, patterns: list[str]) -> str | None:
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def extract_protocol_number(text: str) -> str | None:
    patterns = [
        r'ПРОТОКОЛ\s+ПОВЕРКИ\s+№?\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
        r'Протокол\s+поверки\s+№?\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
        r'№\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
        r'(\d{2}[/-]\d{3,4}[/-]\d{2})',
    ]
    return _match_first(text, patterns)


def extract_serial_number(text: str, filename: str | None = None) -> str | None:
    serial_tok = r'[A-Za-zА-Яа-яЁё0-9\-/]+(?:\s[A-Za-zА-Яа-яЁё0-9\-/]+)?'
    reject_words = r'Год\s+выпуска|наименование|документ|методика|принадлеж|владелец|государств|реестр|аккредит'

    def _clean(serial: str) -> str | None:
        """Clean and validate serial number."""
        # Remove parenthesized content
        serial = re.sub(r'[();]', '', serial)
        # Take only first line (strip everything after \n)
        serial = serial.split('\n')[0]
        # Strip trailing words that look like label fragments
        serial = re.sub(r'\s+(?:Год|заводской|номер|принадлеж|СИ|измерений|поверки)\s*$', '', serial, flags=re.IGNORECASE)
        # Strip trailing single/isolated digits that leaked from tables
        serial = re.sub(r'\s+\d{1,2}$', '', serial)
        # Strip surrounding whitespace and dots
        serial = serial.strip().strip('.').strip('-').strip()
        if not serial or len(serial) <= 1 or len(serial) > 40:
            return None
        if re.search(reject_words, serial, re.IGNORECASE):
            return None
        return serial

    # Pattern B: "заводской номер (номера): VALUE" on same line
    m = re.search(r'заводской\s+номер\s*(?:\(номера\)|\s+СИ)?\s*[:\s]+(' + serial_tok + r')', text, re.IGNORECASE)
    if m:
        s = _clean(m.group(1))
        if s:
            return s

    # Pattern A: VALUE on line BEFORE "заводской номер" (anchored to line start/end)
    m = re.search(
        r'^([A-Za-zА-Яа-яЁё0-9\-/ ]{3,40})\s*$\n\s*заводской\s+номер',
        text, re.IGNORECASE | re.MULTILINE
    )
    if m:
        s = _clean(m.group(1))
        if s:
            return s

    # Pattern A': same but without line-anchor (some PDFs have weird wrapping)
    m = re.search(
        r'([A-Za-zА-Яа-яЁё0-9\-/]{3,30})\s*\n\s*заводской\s+номер',
        text, re.IGNORECASE
    )
    if m:
        s = _clean(m.group(1))
        if s:
            return s

    # Pattern D: from filename
    if filename:
        for pat in [
            r'№\s*([A-Za-zА-Яа-яЁё0-9\-/]+)',
            r'- ([A-Za-zА-Яа-яЁё0-9\-/]+)\s*\(',
        ]:
            m = re.search(pat, filename)
            if m:
                s = _clean(m.group(1))
                if s:
                    return s
    return None


def extract_mit_number(text: str) -> str | None:
    return _match_first(text, [r'(\d{5,6}-\d{2,4})', r'(\d{3,6}-\d{2,4})'])


def extract_manufacture_year(text: str) -> int | None:
    y = _match_first(text, [
        r'(?:\d+\.\s*)?Год\s+выпуска[:\s]+(\d{4})',
        r'(?:\d+\.\s*)?Год\s+изготовления[:\s]+(\d{4})',
    ])
    if y:
        try:
            yi = int(y)
            if 1980 <= yi <= 2030:
                return yi
        except ValueError:
            pass
    return None


def extract_owner(text: str) -> str | None:
    # Stop at colon to avoid eating into the value
    owner = _match_first(text, [
        r'(?:\d+\.\s*)?Принадлеж[^\n:]*[:\s]+([^\n\r]{3,200})',
        r'(?:\d+\.\s*)?Владелец[^\n:]*[:\s]+([^\n\r]{3,200})',
    ])
    if owner:
        # Remove INN/KPP with surrounding punctuation
        owner = re.sub(r'\s*,?\s*ИНН\s*/?\s*КПП?\s*\d*', ' ', owner, flags=re.IGNORECASE)
        # Remove raw INN numbers (10-14 digits)
        owner = re.sub(r'\s+\d{10,14}\s*', ' ', owner)
        owner = re.sub(r'["«»]', '', owner)
        owner = re.split(r'[;,]\s*', owner)[0].strip()
        owner = re.sub(r'\s+', ' ', owner).strip()
    return owner if owner and len(owner) > 3 and not owner.isdigit() else None


def extract_verification_date(text: str) -> str | None:
    conclusion = re.search(r'Заключение:.*?(\n\n|\Z)', text, re.DOTALL)
    stext = conclusion.group(0) if conclusion else text
    # Numeric date: "Дата поверки: 01.12.2025"
    m = re.search(r'Дата\s+поверки[:\s]+(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})', stext)
    if m:
        d, mn, y = m.groups()
        return f"{y}-{mn.zfill(2)}-{d.zfill(2)}"

    last = text[-1200:]
    # Numeric date after "от": "от 11.01.2024"
    m = re.search(r'от\s+(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})', last)
    if m:
        d, mn, y = m.groups()
        return f"{y}-{mn.zfill(2)}-{d.zfill(2)}"

    # Russian month: "20 июня 2024 г."
    m = re.search(r'Дата\s+поверки[:\s]+(\d{1,2})\s+(\w+)\s+(\d{4})', stext)
    if m:
        day, month_ru, year = m.groups()
        month = MONTH_MAP.get(month_ru.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    # Fallback: "11 января 2024" anywhere in last 1200 chars
    m = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', last)
    if m:
        day, month_ru, year = m.groups()
        month = MONTH_MAP.get(month_ru.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"
    return None


def extract_verifier(text: str) -> str | None:
    m = re.search(r'поверитель[:\s]*\n\s*([^\n\r]+)', text, re.IGNORECASE)
    if m:
        v = m.group(1).strip()
        if not re.search(r'подпись|фамилия|инициалы', v, re.IGNORECASE) and len(v) > 3:
            return v
    m = re.search(r'\n\s*([^\n\r]{5,40})\s*\n\s*Поверитель[:\s]*\s*$', text, re.IGNORECASE | re.MULTILINE)
    if m:
        v = m.group(1).strip()
        if len(v) > 3 and not re.search(r'подпись|фамилия|инициалы', v, re.IGNORECASE):
            return v
    return None


def extract_temperature(text: str) -> float | None:
    t = _match_first(text, [r'температура[^\d]*(\d+[\.,]?\d*)\s*°?\s*С', r'температура[^\d]*(\d+[\.,]?\d*)'])
    if t:
        try:
            return float(t.replace(',', '.'))
        except ValueError:
            pass
    return None


def extract_humidity(text: str) -> float | None:
    h = _match_first(text, [r'влажность[^\d]*(\d+[\.,]?\d*)\s*%', r'влажность[^\d]*(\d+[\.,]?\d*)'])
    if h:
        try:
            return float(h.replace(',', '.'))
        except ValueError:
            pass
    return None


def extract_pressure(text: str) -> float | None:
    p = _match_first(text, [r'давление[^\d]*(\d+[\.,]?\d*)', r'Давление\D+(\d+[\.,]?\d*)'])
    if p:
        try:
            return float(p.replace(',', '.'))
        except ValueError:
            pass
    return None


def extract_result(text: str) -> str | None:
    tl = text.lower()
    if 'пригод' in tl or 'соответств' in tl:
        return 'suitable'
    if 'непригод' in tl or 'не соответств' in tl:
        return 'unsuitable'
    return None


def extract_device_name(text: str) -> str | None:
    m = re.search(r'\n([^\n\r]{3,120})\n\s*наименование[,\s]*тип', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return _match_first(text, [r'Наименование[:\s]+([^\n\r]{2,100})'])


def extract_device_type(text: str) -> str | None:
    m = re.search(r'\n([^\n\r]{3,120})\n\s*наименование[,\s]*тип', text, re.IGNORECASE)
    if m:
        line = m.group(1).strip()
        if ',' in line:
            last = line.split(',')[-1].strip()
            if re.search(r'\d', last) or re.match(r'^[A-ZА-Я]{2,}', last):
                return last
    return _match_first(text, [r'Тип[:\s]+([^\n\r]+)', r'Модификация[:\s]+([^\n\r]+)'])


def extract_verification_method(text: str) -> str | None:
    m = re.search(r'Методика\s+поверки[^«"]*[«"]([^»"]{10,200})[»"]', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return _match_first(text, [r'Методика\s+поверки[:\s]+([^\n\r]+)'])


def extract_measurement_range(text: str) -> str | None:
    m = re.search(r'от\s+([\d\.,]+)\s+до\s+([\d\.,]+)\s+([\w/°³²%]{1,20})', text, re.IGNORECASE)
    if m:
        return f"({m.group(1)}-{m.group(2)}) {m.group(3)}"
    return None


FULL_EXTRACTION = {
    "protocol_number": extract_protocol_number,
    "serial_number": extract_serial_number,
    "mit_number": extract_mit_number,
    "manufacture_year": extract_manufacture_year,
    "owner": extract_owner,
    "verification_date": extract_verification_date,
    "verifier": extract_verifier,
    "temperature": extract_temperature,
    "humidity": extract_humidity,
    "pressure": extract_pressure,
    "result": extract_result,
    "device_name": extract_device_name,
    "device_type": extract_device_type,
    "verification_method": extract_verification_method,
    "measurement_range": extract_measurement_range,
}


def extract_all(text: str, filename: str, api_key: str = "") -> dict[str, Any]:
    """Run regex + AI extraction on OCR text."""
    result = {}
    for field, func in FULL_EXTRACTION.items():
        try:
            if field == "serial_number":
                result[field] = func(text, filename)
            else:
                result[field] = func(text)
        except Exception:
            result[field] = None

    # AI fallback for missing fields using free OpenRouter models
    conf = calculate_confidence(result)
    missing = [k for k, v in result.items() if not v]
    if api_key and missing and conf < 0.7:
        print("AI...", end=" ", flush=True)
        ai_data = ai_extract_missing(text, missing, api_key)
        for field in missing:
            if ai_data.get(field) and not result.get(field):
                result[field] = ai_data[field]

    return result


# ── AI Extraction via OpenRouter ───────────────────────────────────────────

AI_SYSTEM_PROMPT = """Извлеки данные из протокола поверки СИ. Верни ТОЛЬКО JSON без markdown.

ПОЛЯ:
- protocol_number: № протокола (формат 02/2208/26)
- device_name: Наименование СИ
- device_type: Тип/модификация
- serial_number: Заводской номер
- mit_number: № в госреестре (формат 60168-15)
- manufacture_year: Год выпуска (число)
- owner: Владелец/организация
- verification_date: Дата поверки (YYYY-MM-DD)
- verifier: ФИО поверителя
- temperature: Температура (°C, число)
- humidity: Влажность (%, число)
- pressure: Давление (кПа, число)
- result: 'suitable' или 'unsuitable'
- verification_method: Методика поверки
- measurement_range: Диапазон измерений

Если поле не найдено — ставь null. Только JSON."""


def ai_extract_missing(text: str, fields: list[str], api_key: str) -> dict[str, Any]:
    """Use OpenRouter free models to extract missing fields."""
    import httpx

    models = [
        "moonshotai/kimi-k2.6:free",
        "google/gemini-2.0-flash-001",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]

    field_hint = ", ".join(fields)
    user_msg = f"Извлеки ТОЛЬКО эти поля: {field_hint}\n\nТекст протокола:\n{text[:4000]}"

    for model in models:
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": AI_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": 600,
                    "temperature": 0.0,
                },
                timeout=35.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Parse JSON from response
            import json as _json
            for candidate in [content, *_extract_json_candidates(content)]:
                try:
                    parsed = _json.loads(candidate)
                    if isinstance(parsed, dict):
                        return {f: parsed.get(f) for f in fields if parsed.get(f)}
                except (_json.JSONDecodeError, TypeError):
                    continue
        except Exception:
            continue
    return {}


def _extract_json_candidates(text: str) -> list[str]:
    """Try to extract JSON from markdown or raw text."""
    import re as _re
    candidates = []
    m = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, _re.DOTALL)
    if m:
        candidates.append(m.group(1))
    m = _re.search(r'(\{.*\})', text, _re.DOTALL)
    if m:
        candidates.append(m.group(1))
    return candidates


def calculate_confidence(data: dict) -> float:
    required = ["protocol_number", "serial_number", "device_name",
                "verification_date", "verifier", "result",
                "owner", "verification_method"]
    optional = ["mit_number", "device_type", "measurement_range"]
    score = sum(2 for f in required if data.get(f))
    score += sum(1 for f in optional if data.get(f))
    return min(1.0, score / (len(required) * 2 + len(optional)))


# ── Phase 1: Sampling ─────────────────────────────────────────────────────

def sample_protocols(base_path: Path, max_total: int = MAX_SAMPLE,
                     per_group: int = SAMPLE_PER_GROUP, seed: int = 42) -> list[dict]:
    random.seed(seed)
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

    sample_pool: list[Path] = []
    for (year, month), files in sorted(groups.items()):
        n = min(per_group, len(files))
        sample_pool.extend(random.sample(files, n))

    if len(sample_pool) > max_total:
        sample_pool = random.sample(sample_pool, max_total)

    random.shuffle(sample_pool)

    result = []
    for path in sample_pool:
        parts = path.relative_to(base_path).parts
        result.append({
            "year": int(parts[0]), "month": int(parts[1]),
            "path": str(path), "filename": path.name, "size": path.stat().st_size,
        })

    print(f"Found {len(groups)} year/month groups, {sum(len(v) for v in groups.values())} total files")
    print(f"Sampled {len(result)} files across {len(set((r['year'],r['month']) for r in result))} groups")
    return result


# ── Phase 4: ARSHIN validation ─────────────────────────────────────────────

def _normalize_serial(s: str) -> str:
    return s.translate(str.maketrans("АВСЕКМНОРТХаеорсух", "ABCEKMHOPTXAEOPCyX"))


async def validate_via_arshin(extracted: dict, text: str) -> dict:
    import httpx

    serial = extracted.get("serial_number")
    if not serial:
        return {"status": "no_serial", "comparisons": {}}

    arshin_url = "https://fgis.gost.ru/fundmetrology/eapi/vri"
    params = {"org_title": 'ООО "МКАИР"', "mi_number": serial, "rows": 5}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(arshin_url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("result", {}).get("items", [])
    except Exception as e:
        return {"status": f"arshin_error", "comparisons": {}, "serial": serial}

    if not items:
        return {"status": "no_arshin_match", "comparisons": {}, "serial": serial}

    arshin = items[0]
    comparisons = {}

    proto_serial = _normalize_serial(str(extracted.get("serial_number", "")).strip())
    arshin_serial = _normalize_serial(arshin.get("mi_number", "").strip())

    comparisons["serial_number"] = {
        "match": proto_serial.lower() == arshin_serial.lower(),
        "extracted": str(extracted.get("serial_number")),
        "arshin": arshin.get("mi_number", ""),
    }

    # MIT number
    proto_mit = str(extracted.get("mit_number") or "")
    arshin_mit = arshin.get("mit_number") or ""
    comparisons["mit_number"] = {
        "match": proto_mit == arshin_mit,
        "extracted": proto_mit,
        "arshin": arshin_mit,
    }

    # Device name — substring match
    proto_name = (extracted.get("device_name") or "").split(";")[0].strip().lower()
    arshin_name = (arshin.get("mit_title") or "").lower()
    comparisons["device_name"] = {
        "match": proto_name and (proto_name in arshin_name or arshin_name in proto_name),
        "extracted": extracted.get("device_name", ""),
        "arshin": arshin.get("mit_title", ""),
    }

    # Date — normalize formats
    proto_date = str(extracted.get("verification_date") or "")
    arshin_date = arshin.get("verification_date") or ""
    proto_clean = proto_date.replace("-", "").replace(".", "")[:8]
    arshin_clean = ""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            arshin_clean = datetime.strptime(arshin_date, fmt).strftime("%Y%m%d")
            break
        except ValueError:
            pass
    comparisons["verification_date"] = {
        "match": proto_clean == arshin_clean,
        "extracted": proto_date,
        "arshin": arshin_date,
    }

    # Result
    proto_result = str(extracted.get("result") or "").lower()
    arshin_result = "suitable" if arshin.get("applicability") else "unsuitable"
    comparisons["result"] = {
        "match": proto_result == arshin_result,
        "extracted": proto_result,
        "arshin": arshin_result,
    }

    # Owner — partial match
    proto_owner = (extracted.get("owner") or "").replace('"', "").replace("«", "").replace("»", "").lower()
    arshin_owner = (arshin.get("org_title") or "").replace('"', "").lower()
    comparisons["owner"] = {
        "match": proto_owner[:20] in arshin_owner or arshin_owner[:20] in proto_owner,
        "extracted": extracted.get("owner", ""),
        "arshin": arshin.get("org_title", ""),
    }

    return {"status": "ok", "serial": serial, "vri_id": arshin.get("vri_id"), "comparisons": comparisons}


# ── Phase 5: Report ────────────────────────────────────────────────────────

def generate_report(results: list[dict], output_dir: Path) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    total = len(results)
    success = sum(1 for r in results if r.get("confidence", 0) >= 0.4)
    ocr_errors = sum(1 for r in results if r.get("ocr_error"))

    # Field accuracy
    field_matches: defaultdict[str, list[bool]] = defaultdict(list)
    validated = 0
    for r in results:
        comps = r.get("validation", {}).get("comparisons", {})
        if comps:
            validated += 1
            for field, comp in comps.items():
                field_matches[field].append(comp.get("match", False))

    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)
    print(f"Files tested:            {total}")
    print(f"Success (conf >= 0.4):   {success} ({success*100//max(total,1)}%)")
    print(f"OCR errors:              {ocr_errors}")
    print(f"ARSHIN validated:        {validated}")
    print()
    print("Field accuracy vs ARSHIN (regex-only, no AI):")
    for field in sorted(field_matches.keys()):
        matches = field_matches[field]
        acc = sum(matches) / len(matches) * 100
        bar = "█" * int(acc / 5) + "░" * (20 - int(acc / 5))
        print(f"  {field:<22s} [{bar}] {acc:5.1f}% ({sum(matches)}/{len(matches)})")
    print("=" * 70)

    # Excel
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill

        wb = Workbook()

        # Sheet 1: Overview
        ws = wb.active
        ws.title = "Overview"
        headers = ["#", "File", "Year", "Month", "Conf", "Protocol#", "Device", "Type",
                    "Serial", "MIT", "YearMfg", "Owner", "Date", "Verifier",
                    "Temp", "Hum", "Pressure", "Result", "Method", "Range",
                    "OCR Pages", "OCR Err", "OCR Text (300ch)"]
        for i, h in enumerate(headers, 1):
            ws.cell(1, i, h).font = Font(bold=True)

        green = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        red = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

        for idx, r in enumerate(results, 1):
            d = r.get("extracted", {}) or {}
            row = [idx, r.get("filename"), r.get("year"), r.get("month"),
                   r.get("confidence"), d.get("protocol_number"), d.get("device_name"),
                   d.get("device_type"), d.get("serial_number"), d.get("mit_number"),
                   d.get("manufacture_year"), d.get("owner"), d.get("verification_date"),
                   d.get("verifier"), d.get("temperature"), d.get("humidity"),
                   d.get("pressure"), d.get("result"), d.get("verification_method"),
                   d.get("measurement_range"), r.get("ocr_pages", 0),
                   r.get("ocr_error", ""), (r.get("ocr_text", "") or "")[:300]]
            for col, val in enumerate(row, 1):
                ws.cell(idx + 1, col, val)
            if r.get("confidence", 0) >= 0.4:
                ws.cell(idx + 1, 5).fill = green
            else:
                ws.cell(idx + 1, 5).fill = red

        # Sheet 2: Validation
        ws2 = wb.create_sheet("ARSHIN Validation")
        for i, h in enumerate(["File", "Serial", "Field", "Match", "Extracted", "ARSHIN"], 1):
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
                ws2.cell(row, 4, "YES" if comp.get("match") else "NO")
                ws2.cell(row, 5, str(comp.get("extracted", ""))[:100])
                ws2.cell(row, 6, str(comp.get("arshin", ""))[:100])
                row += 1

        report_path = output_dir / f"extraction_test_{timestamp}.xlsx"
        wb.save(report_path)
        print(f"\nExcel: {report_path}")
    except ImportError:
        print("\nNo openpyxl")

    # JSON
    json_path = output_dir / f"extraction_test_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"JSON:  {json_path}")
    return str(report_path) if 'report_path' in dir() else ""


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    api_key = OPENROUTER_API_KEY
    ai_label = "+AI" if api_key else "(regex-only)"

    print("=" * 70)
    print(f"metroCheck Extraction Test {ai_label}")
    print("=" * 70)
    print(f"Source:    {PROTOCOLS_PATH}")
    print(f"Output:    {OUTPUT_DIR}")
    print(f"Max files: {MAX_SAMPLE}")
    print(f"API key:   {'set' if api_key else 'NOT SET — skipping AI phase'}")
    print()

    # Phase 1: Sample
    print("── Phase 1: Sampling ──")
    samples = sample_protocols(PROTOCOLS_PATH)

    # Phase 2: OCR + Extract
    print(f"\n── Phase 2: OCR + Extraction ({len(samples)} files) ──")
    results = []
    for i, s in enumerate(samples):
        fpath = s["path"]
        fname = s["filename"]
        print(f"  [{i+1:2d}/{len(samples)}] {fname[:60]}...", end=" ", flush=True)
        t0 = time.time()

        # OCR
        ocr = run_ocr(fpath)
        text = ocr.get("text", "")
        ocr_err = ocr.get("error")

        # Extraction (regex + AI fallback)
        extracted = extract_all(text, fname, api_key)
        conf = calculate_confidence(extracted)

        elapsed = time.time() - t0
        status = "success" if conf >= 0.4 else "manual_review"
        if ocr_err:
            status = "ocr_error"

        print(f"{status} conf={conf:.2f} in {elapsed:.1f}s")

        results.append({
            "year": s["year"], "month": s["month"],
            "filename": fname, "file_path": fpath,
            "ocr_text": text[:500], "ocr_pages": ocr.get("pages", 0),
            "ocr_error": ocr_err, "extracted": extracted,
            "confidence": round(conf, 2), "status": status,
        })

    # Phase 3: Validate via ARSHIN
    print(f"\n── Phase 3: ARSHIN Validation ──")
    for i, r in enumerate(results):
        if r["status"] == "ocr_error":
            continue
        serial = (r.get("extracted") or {}).get("serial_number")
        if not serial:
            print(f"  [{i+1:2d}] {r['filename'][:55]}... no serial — skipping")
            continue
        print(f"  [{i+1:2d}] {r['filename'][:55]}... serial={serial}", end=" ", flush=True)
        try:
            r["validation"] = await validate_via_arshin(r.get("extracted", {}), r.get("ocr_text", ""))
            print(f"→ {r['validation'].get('status')}")
        except Exception as e:
            print(f"ERROR: {e}")

    # Phase 4: Report
    print(f"\n── Phase 4: Report ──")
    generate_report(results, OUTPUT_DIR)
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
