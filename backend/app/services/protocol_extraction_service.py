"""Protocol Extraction Service — regex-based extraction with fallbacks."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class ProtocolExtractionService:
    """Extract protocol data using regex patterns and text analysis."""

    # Russian month mapping
    MONTH_MAP = {
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
    }

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract all protocol data using regex + AI hybrid."""
        if not text:
            return {"content": {}, "status": "manual_review", "cost": 0}

        # Phase 1: Regex extraction (fast, for standard fields)
        data = {
            "protocol_number": self._extract_protocol_number(text),
            "device_name": None,  # Will try AI
            "device_type": None,  # Will try AI
            "serial_number": self._extract_serial_number(text),
            "mit_number": self._extract_mit_number(text),
            "manufacture_year": self._extract_manufacture_year(text),
            "owner": self._extract_owner(text),
            "verification_date": self._extract_verification_date(text),
            "verifier": self._extract_verifier(text),
            "temperature": self._extract_temperature(text),
            "humidity": self._extract_humidity(text),
            "pressure": self._extract_pressure(text),
            "verification_method": self._extract_methodology(text),
            "result": self._extract_result(text),
            "measurement_range": None,  # Will try AI
        }

        # Phase 2: Try regex for device_name and range too
        data["device_name"] = self._extract_device_name(text)
        data["device_type"] = self._extract_device_type(text)
        data["measurement_range"] = self._extract_range(text)

        # Clean all values
        data = {k: self._clean_value(v) for k, v in data.items()}

        # Phase 3: AI fallback for missing complex fields only
        confidence = self._calculate_confidence(data)
        
        if confidence < 0.5:
            # AI only for missing fields
            missing = []
            if not data.get("device_name"):
                missing.append("device_name")
            if not data.get("measurement_range"):
                missing.append("measurement_range")
            if not data.get("device_type"):
                missing.append("device_type")
            
            if missing:
                try:
                    ai_data = await self._ai_extract_fields(text, missing)
                    for field in missing:
                        if ai_data.get(field) and not data.get(field):
                            data[field] = ai_data[field]
                except Exception as e:
                    logger.warning("AI fallback failed: %s", e)

        # Recalculate confidence
        confidence = self._calculate_confidence(data)
        status = "success" if confidence >= 0.4 else "manual_review"

        return {
            "content": data,
            "status": status,
            "cost": 0,
            "attempts": 1,
        }

    async def _ai_extract_fields(self, text: str, fields: list[str]) -> dict[str, Any]:
        """Use AI to extract only specific missing fields."""
        from app.services.ai_extraction_service import get_ai_extraction_service
        
        ai_service = get_ai_extraction_service()
        
        # Build minimal prompt for missing fields only
        field_prompts = {
            "device_name": "Найди наименование средства измерений (одно слово или короткая фраза)",
            "device_type": "Найди тип/модификацию СИ",
            "measurement_range": "Найди диапазон измерений в формате 'от X до Y единица'",
        }
        
        prompts = [field_prompts[f] for f in fields if f in field_prompts]
        if not prompts:
            return {}
        
        prompt = (
            f"Проанализируй протокол поверки и найди:\n"
            f"{'\n'.join(f'{i+1}. {p}' for i, p in enumerate(prompts))}\n\n"
            f"Верни ТОЛЬКО JSON с полями: {', '.join(fields)}.\n"
            f"Без пояснений."
        )
        
        result = await ai_service.extract(
            text=text,
            custom_prompt=prompt,
            models=["nvidia/nemotron-3-super-120b-a12b:free"],
            max_tokens=300,
        )
        
        return result.get("content", {})

    def _extract_protocol_number(self, text: str) -> str | None:
        """Extract protocol number like '12/044/25' or '01/001/24'."""
        patterns = [
            r'ПРОТОКОЛ\s+ПОВЕРКИ\s+№?\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
            r'Протокол\s+поверки\s+№?\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
            r'№\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})\s+от',
            r'№\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
            r'ПРОТОКОЛ\s+№?\s*(\d{1,3}[/-]\d{1,4}[/-]\d{2,4})',
            # Fallback: just look for the pattern anywhere in first 500 chars
            r'(\d{2}[/-]\d{3,4}[/-]\d{2})',
        ]
        return self._match_first(text, patterns)

    def _extract_device_name(self, text: str) -> str | None:
        """Extract device name from 'Наименование средства измерений'."""
        # Look for device name after common headers
        patterns = [
            r'Наименование\s+средства\s+измерений[:\s]+([^\n\r]{2,100})',
            r'Наименование\s+СИ[:\s]+([^\n\r]{2,100})',
            r'Наименование[:\s]+([^\n\r]{2,100})',
        ]
        name = self._match_first(text, patterns)
        if name:
            # Clean up - take first meaningful part
            name = name.strip()
            # Remove common artifacts
            name = re.sub(r'^средств[ао]\s+измерений[:\s]*', '', name, flags=re.IGNORECASE)
            # Take first part before comma or parenthesis
            name = re.split(r'[,;\(\[].*', name)[0].strip()
            return name if len(name) > 2 else None
        return None

    def _extract_device_type(self, text: str) -> str | None:
        """Extract device type/modification."""
        patterns = [
            r'Тип,?\s+модификация\s+средства\s+измерений[:\s]+([^\n\r]+)',
            r'Тип,?\s+модификация[:\s]+([^\n\r]+)',
            r'Тип[:\s]+([^\n\r]+)',
            r'Модификация[:\s]+([^\n\r]+)',
        ]
        return self._match_first(text, patterns)

    def _extract_serial_number(self, text: str) -> str | None:
        """Extract serial number."""
        patterns = [
            r'Заводской\s+номер[:\s]+([^\n\r]+)',
            r'Зав\.\s*№?[:\s]+([^\n\r]+)',
            r'Серийный\s+номер[:\s]+([^\n\r]+)',
            r'№\s*заводской[:\s]+([^\n\r]+)',
        ]
        return self._match_first(text, patterns)

    def _extract_mit_number(self, text: str) -> str | None:
        """Extract MIT number like '47279-11'."""
        # Look in specific sections first
        mit_section = re.search(
            r'(Номер\s+в\s+государственном\s+реестре|реестре\s+СИ|Государственный\s+реестр)[^\n]*(?:\n[^\n]*){0,5}',
            text, re.IGNORECASE
        )
        search_text = mit_section.group(0) if mit_section else text

        patterns = [
            r'(\d{5,6}-\d{2,4})',
            r'(\d{3,6}-\d{2,4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, search_text)
            if match:
                return match.group(1)
        return None

    def _extract_manufacture_year(self, text: str) -> int | None:
        """Extract manufacture year."""
        patterns = [
            r'Год\s+выпуска[:\s]+(\d{4})',
            r'Год\s+изготовления[:\s]+(\d{4})',
            r'Год\s+выпуска\D+(\d{4})',
        ]
        year_str = self._match_first(text, patterns)
        if year_str:
            try:
                year = int(year_str)
                if 1980 <= year <= 2030:
                    return year
            except ValueError:
                pass
        return None

    def _extract_owner(self, text: str) -> str | None:
        """Extract owner organization."""
        # Look for organization name near "Владелец" or standalone
        patterns = [
            r'Принадлежащее[:\s]+([^\n\r]{3,100})',
            r'Владелец\s+средства\s+измерений[:\s]+([^\n\r]{3,100})',
            r'Владелец[:\s]+([^\n\r]{3,100})',
            r'Организация[-\s]*владелец[:\s]+([^\n\r]{3,100})',
            r'Организация[:\s]+([^\n\r]{3,100})',
        ]
        owner = self._match_first(text, patterns)
        if owner:
            # Clean: remove INN, extra text, quotes
            owner = re.sub(r'\s+\d{10,14}\s*', ' ', owner)
            owner = re.sub(r'["«»]', '', owner)
            owner = owner.strip()
            # Stop at first sentence end or common delimiters
            owner = re.split(r'[;,]\s*(?=\d|по\s|с\s|в\s)', owner)[0].strip()
            if len(owner) > 3:
                return owner
        return None

    def _extract_verification_date(self, text: str) -> str | None:
        """Extract verification date in YYYY-MM-DD format."""
        # Pattern: "от 11.01.2024г."
        match = re.search(r'от\s+(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})', text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Pattern: "11 января 2024"
        match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', text)
        if match:
            day, month_ru, year = match.groups()
            month = self.MONTH_MAP.get(month_ru.lower())
            if month:
                return f"{year}-{month}-{day.zfill(2)}"

        # Pattern: "2024-01-11"
        match = re.search(r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})', text)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return None

    def _extract_verifier(self, text: str) -> str | None:
        """Extract verifier name."""
        patterns = [
            r'Поверитель[:\s]+([^\n\r]+)',
            r'Поверитель\s*\n\s*([^\n\r]+)',
            r'Поверител[ьи]\s*:?\s*([^\n\r]+)',
        ]
        verifier = self._match_first(text, patterns)
        if verifier:
            # Clean format: "Чупин А.А." or "Чупин А. А."
            verifier = re.sub(r'([А-Я])\.\s+([А-Я])\.', r'\1.\2.', verifier)
            verifier = verifier.strip()
            if len(verifier) > 3:
                return verifier
        return None

    def _extract_temperature(self, text: str) -> float | None:
        """Extract temperature."""
        patterns = [
            r'температура[^\d]*(\d+[\.,]?\d*)\s*°?\s*С',
            r'температура[^\d]*(\d+[\.,]?\d*)',
            r'Температура\D+(\d+[\.,]?\d*)',
        ]
        temp_str = self._match_first(text, patterns)
        if temp_str:
            try:
                return float(temp_str.replace(',', '.'))
            except ValueError:
                pass
        return None

    def _extract_humidity(self, text: str) -> float | None:
        """Extract humidity."""
        patterns = [
            r'влажность[^\d]*(\d+[\.,]?\d*)\s*%',
            r'влажность[^\d]*(\d+[\.,]?\d*)',
            r'Влажность\D+(\d+[\.,]?\d*)',
        ]
        hum_str = self._match_first(text, patterns)
        if hum_str:
            try:
                return float(hum_str.replace(',', '.'))
            except ValueError:
                pass
        return None

    def _extract_pressure(self, text: str) -> float | None:
        """Extract pressure."""
        patterns = [
            r'давление[^\d]*(\d+[\.,]?\d*)\s*(?:кПа|гПа|hPa)',
            r'давление[^\d]*(\d+[\.,]?\d*)',
            r'Давление\D+(\d+[\.,]?\d*)',
        ]
        press_str = self._match_first(text, patterns)
        if press_str:
            try:
                return float(press_str.replace(',', '.'))
            except ValueError:
                pass
        return None

    def _extract_methodology(self, text: str) -> str | None:
        """Extract verification methodology."""
        patterns = [
            r'Методика\s+поверки[:\s]+([^\n\r]+)',
            r'Методика[:\s]+([^\n\r]+)',
            r'по\s+методике[:\s]+([^\n\r]+)',
            r'документ\s+на\s+методику\s+поверки[:\s]+([^\n\r]+)',
        ]
        method = self._match_first(text, patterns)
        if method:
            # Clean methodology - remove quotes and extra symbols
            method = re.sub(r'^[\s"«»\'„]+|[\s"«»\'„]+$', '', method)
            method = method.strip()
            if len(method) > 5:
                return method
        return None

    def _extract_result(self, text: str) -> str | None:
        """Extract verification result."""
        text_lower = text.lower()
        if 'пригод' in text_lower or 'соответств' in text_lower:
            return 'suitable'
        elif 'непригод' in text_lower or 'не соответств' in text_lower:
            return 'unsuitable'
        return None

    def _extract_range(self, text: str) -> str | None:
        """Extract measurement range."""
        # Pattern 1: Explicit range with "от...до"
        patterns = [
            r'Диапазон\s+измерений.{0,300}?от\s+([\d\.,]+)\s+до\s+([\d\.,]+)\s+([\w/°³²]+)',
            r'от\s+([\d\.,]+)\s+до\s+([\d\.,]+)\s+([\w/°³²]{1,20})',
            # Pattern without "от...до" — just numbers with dash
            r'Диапазон\s+измерений.{0,300}?([\d\.,]+)\s*[-–—]\s*([\d\.,]+)\s+([\w/°³²]{1,20})',
            # Range with unit at the end of section
            r'диапазон.{0,300}?(?:входной|измеряемой|рабочих).{0,200}?([\d\.,]+)\s*[-–—]\s*([\d\.,]+)\s+([\w/°³²]{1,20})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                unit = match.group(3).strip()
                # Clean unit
                unit = re.sub(r'[;,\.\s]+$', '', unit)
                return f"({match.group(1)}-{match.group(2)}) {unit}"
        
        # Pattern 2: Extract from verification table (min/max values)
        # Look for lines with identical first two values (etalon readings)
        table_values = []
        for line in text.split('\n'):
            match = re.match(r'^\s*([\d\.,]+)\s+\1\s+', line)
            if match:
                val = match.group(1).replace(',', '.')
                try:
                    table_values.append(float(val))
                except ValueError:
                    continue
        
        if table_values:
            min_val = min(table_values)
            max_val = max(table_values)
            
            # Find unit from table header
            unit = None
            for pattern in [r'\b(кПа|МПа|bar|Бар|Па|hPa|°C|%)\b']:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    unit = match.group(1)
                    break
            
            if unit:
                # Format values nicely
                min_str = f"{min_val:g}".replace('.', ',')
                max_str = f"{max_val:g}".replace('.', ',')
                return f"({min_str}-{max_str}) {unit}"
        
        return None

    def _match_first(self, text: str, patterns: list[str]) -> str | None:
        """Try patterns and return first match."""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _clean_value(self, value: Any) -> Any:
        """Clean extracted value."""
        if value is None:
            return None
        if isinstance(value, str):
            # Remove surrounding quotes and whitespace
            value = value.strip()
            value = re.sub(r'^[\s"«»\'„\.,]+|[\s"«»\'„\.,]+$', '', value)
            # Replace multiple spaces
            value = re.sub(r'\s+', ' ', value)
            return value if value else None
        return value

    def _calculate_confidence(self, data: dict) -> float:
        """Calculate extraction confidence."""
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


_extraction_service = None


def get_protocol_extraction_service():
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ProtocolExtractionService()
    return _extraction_service


# Also provide async wrapper for compatibility
class SmartExtractor:
    """Async wrapper for ProtocolExtractionService."""

    def __init__(self) -> None:
        self.service = get_protocol_extraction_service()

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract protocol data using regex + AI hybrid."""
        return await self.service.extract(text)


def get_smart_extractor():
    return SmartExtractor()
