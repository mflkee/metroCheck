"""Protocol Extraction Service — multi-pass AI extraction with validation."""

import asyncio
import json
import logging
import re
from typing import Any, Optional

from app.services.ai_extraction_service import get_ai_extraction_service

logger = logging.getLogger(__name__)

# Field-specific extraction prompts for retry
FIELD_PROMPTS = {
    "mit_number": (
        "Find the MIT (государственный реестр СИ) number in this protocol. "
        "Look for patterns like: 'номер по Государственному реестру СИ РФ', '№ в реестре', "
        "or standalone numbers like '47279-11', '62301-15'. "
        "Return ONLY the number, nothing else."
    ),
    "measurement_range": (
        "Find the measurement range (диапазон измерений) in this protocol. "
        "Look for: 'Диапазон измерений', 'Установленный диапазон', 'от X до Y', 'входной измеряемой величины'. "
        "Return the range in format like '(4-400) м³/ч' or '-50…+250 °С'. "
        "Return ONLY the range, nothing else."
    ),
    "result": (
        "Find the verification result in this protocol. "
        "Look for: 'пригоден', 'непригоден', 'соответствует', 'признано пригодным'. "
        "Return ONLY 'suitable' or 'unsuitable'."
    ),
    "verification_date": (
        "Find the verification date in this protocol. "
        "Look for: 'Дата поверки', 'Протокол поверки № ... от'. "
        "Return ONLY the date in YYYY-MM-DD format."
    ),
    "verifier": (
        "Find the verifier name (поверитель) in this protocol. "
        "Look for: 'Поверитель:', 'Ф.И.О.', or signature lines. "
        "Return ONLY the name in format 'Фамилия И.О.'."
    ),
    "device_type": (
        "Find the specific device type/modification in this protocol. "
        "This is usually more specific than the device name. "
        "Look for: 'Тип', 'Модификация', 'Обозначение'. "
        "Return ONLY the type, nothing else."
    ),
}


class ProtocolExtractionService:
    """Multi-pass protocol extraction with validation and retry."""

    def __init__(self) -> None:
        self.ai_service = get_ai_extraction_service()

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract all protocol data with validation and retry.
        
        Pipeline:
        1. Initial extraction with full prompt
        2. Validate each field against raw text
        3. Retry missing fields with targeted prompts
        4. Final validation
        """
        # Phase 1: Initial extraction
        result = await self.ai_service.extract(text)
        data = result.get("content") or {}
        
        if not data:
            logger.warning("Initial extraction failed completely")
            return self._build_result(data, result, "manual_review")
        
        # Phase 2: Validate and retry missing fields
        missing_fields = self._find_missing_fields(data)
        
        if missing_fields:
            logger.info("Retrying %d missing fields: %s", len(missing_fields), missing_fields)
            for field in missing_fields:
                value = await self._extract_field(text, field)
                if value:
                    data[field] = value
                    logger.debug("Field %s extracted on retry: %s", field, value)
        
        # Phase 3: Post-process and validate
        data = self._post_process(data, text)
        
        # Calculate final confidence
        confidence = self._calculate_confidence(data)
        
        status = "success" if confidence >= 0.5 else "manual_review"
        
        return self._build_result(data, result, status)

    def _find_missing_fields(self, data: dict) -> list[str]:
        """Find fields that are missing or suspicious."""
        missing = []
        critical_fields = ["serial_number", "verification_date", "verifier", "result"]
        important_fields = ["mit_number", "device_type", "measurement_range"]
        
        for field in critical_fields:
            if not data.get(field):
                missing.append(field)
        
        for field in important_fields:
            if not data.get(field):
                missing.append(field)
        
        return missing

    async def _extract_field(self, text: str, field: str) -> Any:
        """Extract a single field with targeted prompt."""
        prompt = FIELD_PROMPTS.get(field)
        if not prompt:
            return None
        
        try:
            # Use free model for retry
            models = ["nvidia/nemotron-3-super-120b-a12b:free"]
            
            for model in models:
                try:
                    result = await self.ai_service.extract(
                        text=text,
                        models=[model],
                        max_tokens=200,
                        temperature=0.0,
                    )
                    
                    if result.get("content") and result["content"].get(field):
                        return result["content"][field]
                    
                    # If AI returns something else, try to use it
                    if result.get("content"):
                        # The response might be a dict with the field, or just a string
                        content = result["content"]
                        if isinstance(content, dict) and field in content:
                            return content[field]
                        elif isinstance(content, dict) and len(content) == 1:
                            # Single field response
                            return list(content.values())[0]
                        
                except Exception as e:
                    logger.debug("Field extraction %s with %s failed: %s", field, model, e)
                    continue
            
            return None
        except Exception as e:
            logger.warning("Field extraction %s failed: %s", field, e)
            return None

    def _post_process(self, data: dict, text: str) -> dict:
        """Post-process extracted data."""
        # Fix result values
        result = data.get("result")
        if result and isinstance(result, str):
            result_lower = result.lower()
            if "пригод" in result_lower or "соответств" in result_lower:
                data["result"] = "suitable"
            elif "непригод" in result_lower or "не соответств" in result_lower:
                data["result"] = "unsuitable"
        
        # Fix date format
        vdate = data.get("verification_date")
        if vdate and isinstance(vdate, str):
            # Try to parse Russian date format
            for fmt in ["%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d"]:
                try:
                    from datetime import datetime
                    parsed = datetime.strptime(vdate.strip(), fmt)
                    data["verification_date"] = parsed.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
        
        # Extract measurement_range from text if missing
        if not data.get("measurement_range"):
            mr = self._extract_measurement_range_regex(text)
            if mr:
                data["measurement_range"] = mr
        
        # Extract mit_number from text if missing
        if not data.get("mit_number"):
            mit = self._extract_mit_number_regex(text)
            if mit:
                data["mit_number"] = mit
        
        return data

    def _extract_measurement_range_regex(self, text: str) -> str | None:
        """Extract measurement range using regex fallback."""
        # Pattern 1: "Диапазон измерений... от X до Y"
        patterns = [
            r'Диапазон\s+измерений.{0,200}?от\s+([\d\-–]+)\s+до\s+([\d\-–]+)\s+([^\n]+)',
            r'Установленный\s+диапазон.{0,200}?входной\s+измеряемой\s+величины.{0,50}([\d\-–\.]+…[\+\d\-–\.]+)',
            r'от\s+([\d\-–]+)\s+до\s+([\d\-–]+)\s+([^\n]{1,30})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                if len(match.groups()) == 3:
                    return f"({match.group(1)}-{match.group(2)}) {match.group(3).strip()}"
                else:
                    return match.group(1).strip()
        
        return None

    def _extract_mit_number_regex(self, text: str) -> str | None:
        """Extract MIT number using regex fallback."""
        # Look for patterns like "47279-11" near "реестр" or standalone
        patterns = [
            r'номер\s+по\s+Государственному\s+реестру[^\n]*\n\s*(\d{3,6}-\d{2,4})',
            r'реестру\s+СИ\s+РФ[^\n]*\n\s*(\d{3,6}-\d{2,4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        
        # Fallback: standalone number on its own line
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if 'реестр' in line.lower() or 'реестру' in line.lower():
                # Check next few lines
                for j in range(i+1, min(i+3, len(lines))):
                    match = re.match(r'^\s*(\d{3,6}-\d{2,4})\s*$', lines[j])
                    if match:
                        return match.group(1).strip()
        
        return None

    def _calculate_confidence(self, data: dict) -> float:
        """Calculate extraction confidence score."""
        required = [
            "protocol_number", "serial_number", "device_name",
            "verification_date", "verifier", "result",
        ]
        optional = ["mit_number", "device_type", "measurement_range"]
        
        score = 0
        for field in required:
            if data.get(field):
                score += 2
        
        for field in optional:
            if data.get(field):
                score += 1
        
        max_score = len(required) * 2 + len(optional)
        return min(1.0, score / max_score)

    def _build_result(self, data: dict, ai_result: dict, status: str) -> dict[str, Any]:
        """Build final result dict."""
        return {
            "content": data,
            "model": ai_result.get("model"),
            "status": status,
            "cost": ai_result.get("cost", 0.0),
            "attempts": ai_result.get("attempts", 0) + 1,  # +1 for retry
            "usage": ai_result.get("usage"),
        }


_extraction_service: Optional[ProtocolExtractionService] = None


def get_protocol_extraction_service() -> ProtocolExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ProtocolExtractionService()
    return _extraction_service
