"""Smart protocol extraction — regex + AI hybrid with vision fallback."""

import asyncio
import json
import logging
import re
from typing import Any
from datetime import datetime

from app.services.ai_extraction_service import get_ai_extraction_service

logger = logging.getLogger(__name__)

# Regex patterns for Russian protocol fields
REGEX_PATTERNS = {
    "protocol_number": [
        r'ПРОТОКОЛ\s+ПОВЕРКИ\s+№\s*([\w\-/]+)',
        r'протокол\s+поверки\s+№\s*([\w\-/]+)',
    ],
    "serial_number": [
        r'Заводской\s+номер\s*\(?номера\)?\s*[:;]\s*([\w\-]+)',
        r'заводской\s+номер\s*[:;]\s*([\w\-]+)',
        r'№\s*[:;]?\s*([A-ZА-Я]\d{3,})',
        r'[Сс]ерийный\s+номер\s*[:;]\s*([\w\-]+)',
    ],
    "verification_date": [
        r'Дата\s+поверки\s*[:;]\s*(\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4})',
        r'ПРОТОКОЛ\s+ПОВЕРКИ\s+№\s*[\w\-/]+\s+от\s+(\d{1,2}[\.\-/]\d{1,2}[\.\-/]\d{2,4})',
    ],
    "mit_number": [
        r'номер\s+по\s+Государственному\s+реестру\s+СИ\s+РФ\s*\n\s*(\d{3,6}-\d{2,4})',
        r'реестру\s+СИ\s+РФ\s*\n\s*(\d{3,6}-\d{2,4})',
        r'(?m)^\s*(\d{5,6}-\d{2,4})\s*$',
    ],
    "manufacture_year": [
        r'[Гг]од\s+выпуска\s*[:;]\s*(\d{4})',
        r'[Гг]од\s+изготовления\s*[:;]\s*(\d{4})',
    ],
    "owner": [
        r'[Пп]ринадлежащее\s*[:;]\s*([^\n,]+)',
        r'[Вв]ладелец\s+средства\s+измерений\s*[:;]\s*([^\n,]+)',
        r'[Пп]ринадлежит\s*[:;]\s*([^\n,]+)',
    ],
    "verifier": [
        r'[Пп]оверитель\s*[:;]\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)',
        r'[Пп]оверитель\s*\n+\s*([А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.[А-ЯЁ]\.)',
    ],
    "temperature": [
        r'[Тт]емпература\s+окружающей?\s+среды?[^\d]*([\d\,\.]+)',
        r'[Тт]емпература\s+окружающего\s+воздуха[^\d]*([\d\,\.]+)',
    ],
    "humidity": [
        r'[Оо]тносительная\s+влажность[^\d]*([\d\,\.]+)',
        r'[Вв]лажность\s+воздуха[^\d]*([\d\,\.]+)',
    ],
    "pressure": [
        r'[Аа]тмосферное\s+давление[^\d]*([\d\,\.]+)',
        r'[Дд]авление[^\d]*([\d\,\.]+)\s*кПа',
    ],
    "measurement_range": [
        r'[Дд]иапазон\s+измерений[^\n]{0,200}?от\s+([\d\-–\.]+)\s+до\s+([\d\-–\.]+)\s+([^\n]{1,40})',
        r'[Уу]становленный\s+диапазон[^\n]{0,200}?([\d\-–\.]+…[\+\d\-–\.\s]+°?[СC]?)',
        r'входной\s+измеряемой\s+величины[^\n]{0,100}?([\d\-–\.]+…[\+\d\-–\.\s]+°?[СC]?)',
        r'Верхний\s+предел\s+измерения[^\n]{0,100}?(\d+)[^\n]{0,50}?(°?[СC])',
    ],
    "result": [
        r'[Пп]ризнано\s+(пригодным|непригодным)',
        r'[Сс]И\s+признано\s+(пригодным|непригодным)',
        r'[Рр]езультат\s*[:;]\s*(пригоден|непригоден|соответствует|не соответствует)',
    ],
}


def extract_with_regex(text: str) -> dict[str, Any]:
    """Extract fields using regex patterns."""
    result = {}
    
    for field, patterns in REGEX_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                if field == "measurement_range" and len(match.groups()) >= 3:
                    result[field] = f"({match.group(1)}-{match.group(2)}) {match.group(3).strip()}"
                elif field == "result":
                    val = match.group(1).lower()
                    if "пригод" in val or "соответств" in val:
                        result[field] = "suitable"
                    elif "непригод" in val or "не соответств" in val:
                        result[field] = "unsuitable"
                elif field == "verification_date":
                    result[field] = parse_date(match.group(1))
                elif field in ["temperature", "humidity", "pressure"]:
                    try:
                        result[field] = float(match.group(1).replace(',', '.'))
                    except (ValueError, TypeError):
                        result[field] = match.group(1)
                else:
                    result[field] = match.group(1).strip()
                break
    
    return result


def parse_date(date_str: str) -> str | None:
    """Parse Russian date string to ISO format."""
    date_str = date_str.strip()
    
    # Replace Cyrillic month names
    month_map = {
        'янв': '01', 'фев': '02', 'мар': '03', 'апр': '04',
        'май': '05', 'июн': '06', 'июл': '07', 'авг': '08',
        'сен': '09', 'окт': '10', 'ноя': '11', 'дек': '12',
    }
    
    for rus, num in month_map.items():
        date_str = date_str.lower().replace(rus, num)
    
    formats = [
        "%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y",
        "%d.%m.%y", "%d-%m-%y", "%d/%m/%y",
        "%Y-%m-%d", "%Y.%m.%d",
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # Fix 2-digit years
            if dt.year < 50:
                dt = dt.replace(year=dt.year + 2000)
            elif dt.year < 100:
                dt = dt.replace(year=dt.year + 1900)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return None


class SmartExtractor:
    """Hybrid extraction: regex first, AI for missing fields."""
    
    def __init__(self) -> None:
        self.ai_service = get_ai_extraction_service()
    
    async def extract(self, text: str) -> dict[str, Any]:
        """Extract all fields using hybrid approach."""
        
        # Phase 1: Regex extraction (fast, reliable)
        regex_data = extract_with_regex(text)
        logger.info("Regex extracted %d fields", len(regex_data))
        
        # Phase 2: AI extraction for missing fields and complex data
        try:
            ai_result = await asyncio.wait_for(self.ai_service.extract(text), timeout=90.0)
        except asyncio.TimeoutError:
            logger.error("AI extraction timed out after 90s")
            ai_result = {"content": None, "model": None, "status": "manual_review", "cost": 0.0, "attempts": 0, "usage": None}
        ai_data = ai_result.get("content") or {}
        
        # Phase 3: Merge — regex wins for precision, AI fills gaps
        merged = dict(ai_data)  # Start with AI
        for field, value in regex_data.items():
            if value is not None:  # Regex found something
                merged[field] = value
                logger.debug("Regex override for %s: %s", field, value)
        
        # Phase 4: Post-process
        merged = self._post_process(merged)
        
        # Calculate confidence
        confidence = self._calculate_confidence(merged)
        
        return {
            "content": merged,
            "model": ai_result.get("model"),
            "status": "success" if confidence >= 0.5 else "manual_review",
            "cost": ai_result.get("cost", 0.0),
            "attempts": ai_result.get("attempts", 0),
            "usage": ai_result.get("usage"),
            "confidence": confidence,
            "regex_fields": len(regex_data),
        }
    
    def _post_process(self, data: dict) -> dict:
        """Clean and normalize extracted data."""
        # Ensure result is standardized
        result = data.get("result")
        if result and isinstance(result, str):
            val = result.lower()
            if any(w in val for w in ["пригод", "соответств", "suitable", "pass"]):
                data["result"] = "suitable"
            elif any(w in val for w in ["непригод", "не соответств", "unsuitable", "fail"]):
                data["result"] = "unsuitable"
        
        # Clean measurement_range
        if data.get("measurement_range"):
            mr = str(data["measurement_range"])
            # Remove excessive spaces and normalize
            mr = re.sub(r'\s+', ' ', mr).strip()
            if mr.endswith(' +'):
                mr = mr[:-2].strip()
            data["measurement_range"] = mr
        
        # Ensure pressure_units
        if data.get("pressure") and not data.get("pressure_units"):
            if "кПа" in str(data.get("raw_text", "")) or "kPa" in str(data.get("raw_text", "")):
                data["pressure_units"] = "kPa"
            elif "мм рт" in str(data.get("raw_text", "")) or "mmHg" in str(data.get("raw_text", "")):
                data["pressure_units"] = "mmHg"
        
        # Clean owner - remove INN and extra info
        if data.get("owner"):
            owner = str(data["owner"])
            # Remove everything after comma
            owner = owner.split(',')[0].strip()
            # Remove INN reference
            owner = re.sub(r'\s*ИНН\s*\d+', '', owner).strip()
            data["owner"] = owner
        
        return data
    
    def _calculate_confidence(self, data: dict) -> float:
        """Calculate confidence based on filled fields."""
        critical = ["serial_number", "protocol_number", "verification_date", "result"]
        important = ["device_name", "verifier", "temperature", "humidity", "pressure"]
        optional = ["mit_number", "device_type", "measurement_range", "owner"]
        
        score = 0
        for field in critical:
            if data.get(field):
                score += 3
        for field in important:
            if data.get(field):
                score += 2
        for field in optional:
            if data.get(field):
                score += 1
        
        max_score = len(critical) * 3 + len(important) * 2 + len(optional)
        return round(score / max_score, 2)


_extractor: SmartExtractor | None = None


def get_smart_extractor() -> SmartExtractor:
    global _extractor
    if _extractor is None:
        _extractor = SmartExtractor()
    return _extractor
