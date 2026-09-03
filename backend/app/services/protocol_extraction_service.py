"""Protocol Extraction Service — regex-based extraction with fallbacks."""

import logging
import os
import re
from typing import Any

from app.utils import normalize_verifier

logger = logging.getLogger(__name__)

DISABLE_AI = os.environ.get("METROCHECK_DISABLE_AI", "").lower() in ("1", "true", "yes")


class ProtocolExtractionService:
    """Extract protocol data using regex patterns and text analysis."""

    # Russian month mapping
    MONTH_MAP = {
        'января': '01', 'февраля': '02', 'марта': '03', 'апреля': '04',
        'мая': '05', 'июня': '06', 'июля': '07', 'августа': '08',
        'сентября': '09', 'октября': '10', 'ноября': '11', 'декабря': '12',
    }

    async def extract(self, text: str, file_name: str | None = None, file_path: str | None = None) -> dict[str, Any]:
        """Extract all protocol data using regex + AI hybrid.

        For image files (JPG/PNG), falls back to vision LLM if regex+OCR fails.
        """
        if not text:
            return {"content": {}, "status": "manual_review", "cost": 0}

        # Phase 1: Regex extraction (fast, for standard fields)
        data = {
            "protocol_number": self._extract_protocol_number(text),
            "device_name": None,  # Will try AI
            "device_type": None,  # Will try AI
            "serial_number": self._extract_serial_number(text, file_name),
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
        data["measurement_range"] = self._extract_range(text, file_path)

        # Clean all values
        data = {k: self._clean_value(v) for k, v in data.items()}

        # Phase 3: AI fallback — only when necessary and not disabled
        missing = [k for k, v in data.items() if not v]
        hard_critical = {"serial_number", "verification_date", "result"}
        pre_confidence = self._calculate_confidence(data)
        cost = 0.0
        model = None
        ai_used = False

        # Skip LLM if confidence is already high and no hard-critical field is missing
        should_use_llm = bool(
            missing
            and (
                pre_confidence < 0.7
                or (hard_critical & set(missing))
                or {"owner", "verification_method"} & set(missing)
            )
        )

        if should_use_llm and not DISABLE_AI:
            ai_used = True
            try:
                ai_result = await self._ai_extract_fields(text, missing)
                ai_data = ai_result.get("content") or {}
                for field in missing:
                    if ai_data.get(field) and not data.get(field):
                        data[field] = ai_data[field]
                filled = {f: data[f] for f in missing if data.get(f)}
                if filled:
                    self._log_ai_fallback(file_name or "unknown", filled, text)
                    cost = ai_result.get("cost", 0.0)
                    model = ai_result.get("model")
            except Exception as e:
                logger.warning("AI fallback failed: %s", e)

        # Phase 4: Vision model fallback for images with poor results
        confidence = self._calculate_confidence(data)
        if not DISABLE_AI and confidence < 0.35 and file_path:
            ext = os.path.splitext(file_path)[1].lower()
            if ext in {".jpg", ".jpeg", ".png"}:
                ai_used = True
                try:
                    from app.services.ai_extraction_service import get_ai_extraction_service
                    ai_service = get_ai_extraction_service()
                    vision_result = await ai_service.extract_from_image(
                        image_path=file_path,
                        hint_text=text[:2000],
                    )
                    if vision_result.get("status") == "success" and vision_result.get("content"):
                        vision_data = vision_result["content"]
                        for field in missing:
                            if vision_data.get(field) and not data.get(field):
                                data[field] = vision_data[field]
                        cost = vision_result.get("cost", 0.0)
                        model = vision_result.get("model")
                        # Recalculate confidence
                        confidence = self._calculate_confidence(data)
                except Exception as e:
                    logger.warning("Vision model fallback failed for %s: %s", file_path, e)

        status = "success" if confidence >= 0.4 else "manual_review"
        model_used = model if ai_used and model else ("ai" if ai_used else "regex")

        return {
            "content": data,
            "status": status,
            "cost": cost,
            "attempts": 1,
            "confidence": round(confidence, 2),
            "model_used": model_used,
        }

    async def _ai_extract_fields(self, text: str, fields: list[str]) -> dict[str, Any]:
        """Use AI to extract only specific missing fields."""
        from app.services.ai_extraction_service import get_ai_extraction_service

        ai_service = get_ai_extraction_service()

        result = await ai_service.extract(
            text=text,
            max_tokens=600,
        )

        return result

    def _log_ai_fallback(self, file_name: str, filled: dict[str, Any], text: str) -> None:
        """Log AI fallback usage so patterns can be reviewed & added later."""
        field_kwargs = {
            "device_name": ["наименование", "средство", "измерений", "си"],
            "device_type": ["тип", "модификация"],
            "serial_number": ["заводской", "номер", "серийн", "№"],
            "mit_number": ["реестр", "госреестр"],
            "manufacture_year": ["год выпуска", "дата выпуска", "изготовления"],
            "owner": ["владелец", "принадлежн", "организация"],
            "verification_method": ["методик", "документ", "поверк"],
            "verifier": ["поверитель"],
            "measurement_range": ["диапазон"],
        }
        snippet_parts = []
        for field in filled:
            keywords = field_kwargs.get(field, [field])
            for kw in keywords:
                idx = text.lower().find(kw)
                if idx >= 0:
                    start = max(0, idx - 60)
                    end = min(len(text), idx + 140)
                    snippet = text[start:end].replace("\n", "↵")
                    snippet_parts.append(f"[{field}]...{snippet}...")
                    break
        snippet_str = " | ".join(snippet_parts) if snippet_parts else "(no context found)"

        logger.info(
            "AI_FALLBACK file=%s fields=%s snippet=%s",
            file_name, filled, snippet_str,
        )

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
        """Extract device name."""
        candidates = []

        # Pattern A: line(s) BEFORE "наименование, тип" label
        match = re.search(
            r'\n([^\n\r]{3,120})\n([^\n\r]{3,120})\n\s*наименование[,\s]*тип',
            text, re.IGNORECASE
        )
        if match:
            prev_line = match.group(1).strip()
            line = match.group(2).strip()
            if (
                line
                and line[0].islower()
                and not re.search(
                    r'протокол|аккредитации|реестр|уникальный|номер|заводской|год|владел|принадлеж|документ|методик|норматив',
                    prev_line,
                    re.IGNORECASE,
                )
            ):
                candidates.append(prev_line + ' ' + line)
            candidates.append(line)
        else:
            match = re.search(r'\n([^\n\r]{3,120})\n\s*наименование[,\s]*тип', text, re.IGNORECASE)
            if match:
                candidates.append(match.group(1).strip())

        # Pattern B: "Наименование прибора X"
        match = re.search(r'Наименование\s+прибора[:\s]+([^\n\r]{2,100})', text, re.IGNORECASE)
        if match:
            candidates.append(match.group(1).strip())

        # Pattern C: "Наименование, тип, модификация: X"
        match = re.search(r'Наименование[,\s]+тип[^:\n]*:\s*([^\n\r]{2,100})', text, re.IGNORECASE)
        if match:
            candidates.append(match.group(1).strip())

        # Pattern D: explicit labels
        for pattern in [
            r'Наименование\s+средства\s+измерений[:\s]+([^\n\r]{2,100})',
            r'Наименование\s+СИ[:\s]+([^\n\r]{2,100})',
            r'Наименование[:\s]+([^\n\r]{2,100})',
        ]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidates.append(match.group(1).strip())

        # Helpers
        junk_prefixes = ('прибора', 'средства', 'нормативного', 'документа', 'методики', 'поверки')
        device_keywords = (
            'преобразователь', 'датчик', 'термометр', 'термопреобразователь',
            'уровнемер', 'расходомер', 'счетчик', 'манометр', 'вольтметр',
            'амперметр', 'анализатор', 'система', 'измеритель', 'регулятор',
            'клапан', 'преобразователи', 'датчики', 'термометры',
        )

        def _split_glued_words(name: str) -> str:
            # Split Cyrillic word glued to Latin/digits: "давленияМетран" -> "давления Метран"
            # Use explicit ranges without IGNORECASE so only real script transitions match.
            name = re.sub(r'([а-яё])([A-Za-z0-9])', r'\1 \2', name)
            name = re.sub(r'([A-Za-z0-9])([а-яё])', r'\1 \2', name)
            # Also handle Latin glued to Cyrillic capital if any
            name = re.sub(r'([А-ЯЁ])([A-Za-z0-9])', r'\1 \2', name)
            name = re.sub(r'([A-Za-z0-9])([А-ЯЁ])', r'\1 \2', name)
            return name

        def _score_candidate(name: str) -> int:
            lower = name.lower()
            score = 0
            if any(k in lower for k in device_keywords):
                score += 3
            if re.search(r'[а-яё]{4,}', lower):
                score += 1
            if re.match(r'^(протокол|аккред|реестр|уникальный|заводской|год|владел|принадлеж|документ|методик|норматив)', lower):
                score -= 5
            if len(name) >= 10 and len(name) <= 120:
                score += 1
            return score

        scored = []
        for raw in candidates:
            name = raw
            name = re.sub(r'^средств[ао]\s+измерений[:\s]*', '', name, flags=re.IGNORECASE)
            name = re.sub(r'^прибора\s+', '', name, flags=re.IGNORECASE)
            name = re.sub(r'^типа', '', name, flags=re.IGNORECASE).strip()

            # Split glued words first
            name = _split_glued_words(name)

            # Split by semicolon: first part is usually the name
            if ';' in name:
                name = name.split(';')[0].strip()

            # Split by comma for model codes
            while ',' in name:
                parts = [p.strip() for p in name.split(',')]
                last = parts[-1]
                before = parts[-2] if len(parts) >= 2 else ''
                generic_abbrev = re.match(r'^[А-ЯA-Z]{2,4}$', last) and not re.search(r'\d', last)
                if generic_abbrev:
                    name = ','.join(parts[:-1]).strip()
                    break
                mod_series = re.match(r'^([А-ЯA-Z]{2,4})\s+серия$', last)
                if mod_series:
                    name = ','.join(parts[:-1]).strip()
                    break
                if 'и' in before or 'и' in last:
                    break
                if len(last) <= 30 and (
                    re.search(r'\d', last)
                    or re.search(r'[-/]', last)
                    or re.match(r'^[A-ZА-Я]{2,}\s*\d', last)
                ):
                    name = ','.join(parts[:-1]).strip()
                else:
                    break

            # Remove trailing model tokens
            words = name.split()
            while len(words) >= 2:
                last = words[-1]
                prev = words[-2]
                m = re.match(r'^([A-Za-zА-Яа-яЁё]{3,})(\d[\w\.\-/]*)$', last)
                if m:
                    words[-1] = m.group(1)
                    break
                common_prefixes = ('измерительный', 'преобразователь', 'давления', 'уровня',
                                   'температуры', 'расхода', 'типа', 'модель', 'серии', 'серия', 'тип')
                prefix_re = '|'.join(re.escape(p) for p in common_prefixes)
                m2 = re.match(rf'^({prefix_re})([A-ZА-Я0-9][A-Za-zА-Яа-яЁё0-9\.\-/]*)$', last)
                if m2:
                    words[-1] = m2.group(1)
                    break
                is_generic_abbrev = (
                    re.match(r'^[A-ZА-Я]{2,4}$', last)
                    and not re.search(r'\d', last)
                    and len(last) <= 4
                )
                if is_generic_abbrev and (prev == 'и' or prev.endswith(',') or prev.lower() == 'и'):
                    break
                if is_generic_abbrev:
                    words.pop()
                    continue
                if last.lower() == 'серия' and re.match(r'^[A-ZА-Я]{2,4}$', prev):
                    words.pop()
                    continue
                if re.match(r'^[A-Za-zА-Яа-яЁё0-9\.\-/]+$', last) and (
                    re.search(r'\d', last) or re.match(r'^[A-ZА-Я]{2,}', last)
                ):
                    words.pop()
                elif len(words) >= 3 and re.match(r'^\d+$', prev) and re.match(r'^\d[\d\.]+$', last):
                    words.pop()
                    words.pop()
                else:
                    break
            name = ' '.join(words)

            if name.lower().startswith(junk_prefixes):
                continue
            if len(name) <= 2:
                continue
            scored.append((_score_candidate(name), name))

        if not scored:
            return None
        scored.sort(key=lambda x: (-x[0], -len(x[1])))
        return scored[0][1]

    def _extract_device_type(self, text: str) -> str | None:
        """Extract device type/modification."""
        # Pattern A: type on the line AFTER a "наименование, тип, модификация:" block
        match = re.search(
            r'Наименование[,\s]+тип[^:\n]*:\s*[^\n\r]+\n\s*([^\n\r]{2,60})',
            text, re.IGNORECASE
        )
        if match:
            val = match.group(1).strip()
            if not re.search(r'^\d+\.|^(?:Заводской|Дата|Регистрационный|Принадлеж)', val, re.IGNORECASE):
                return val

        # Pattern B: from the device name line, extract the type part
        match = re.search(r'\n([^\n\r]{3,120})\n\s*наименование[,\s]*тип', text, re.IGNORECASE)
        if match:
            line = match.group(1).strip()
            # Semicolon: second part is usually type
            if ';' in line:
                type_part = line.split(';', 1)[1].strip()
                if len(type_part) > 1:
                    return type_part

            # Comma: last comma-separated chunk that looks like a model
            if ',' in line:
                parts = [p.strip() for p in line.split(',')]
                description_markers = {'если', 'входят', 'автономных', 'состав', 'перечень', 'согласно'}
                for part in reversed(parts[1:]):
                    lowered = part.lower()
                    if any(m in lowered for m in description_markers):
                        continue
                    if re.search(r'\d', part) or re.match(r'^[A-ZА-Я]{2,}', part):
                        clean = re.split(r'\s+(?:если|входят|согласно|состав)', part, flags=re.IGNORECASE)[0]
                        return clean.strip() if len(clean.strip()) > 1 else None

            # No comma/semicolon — trailing model-like tokens
            words = line.split()
            type_words: list[str] = []
            # Collect trailing words that look like model codes
            for w in reversed(words):
                # Handle glued tokens like "измерительный3051S" or "типаAPR"
                m = re.match(r'^([a-zа-яё]+?)([A-ZА-Я0-9][A-Za-zА-Яа-яЁё0-9\.\-/]*)$', w)
                if m:
                    common_prefixes = ('измерительный', 'преобразователь', 'давления', 'уровня',
                                       'температуры', 'расхода', 'типа', 'модель', 'серии', 'серия', 'тип')
                    if m.group(1).lower() in common_prefixes:
                        type_words.insert(0, m.group(2))
                    else:
                        type_words.insert(0, w)
                    continue
                if re.match(r'^[A-Za-zА-Яа-яЁё0-9\.\-/]+$', w) and (re.search(r'\d', w) or re.match(r'^[A-ZА-Я]{2,}', w)) or w.isdigit() and type_words:
                    type_words.insert(0, w)
                else:
                    break
            if type_words and len(' '.join(type_words)) > 1:
                # Also include a preceding digit if present (e.g. "2 232.50.160")
                idx = len(words) - len(type_words)
                if idx > 0 and re.match(r'^\d+$', words[idx - 1]):
                    type_words.insert(0, words[idx - 1])
                return ' '.join(type_words)

        patterns = [
            r'Тип,?\s+модификация\s+средства\s+измерений[:\s]+([^\n\r]+)',
            r'Тип,?\s+модификация[:\s]+([^\n\r]+)',
            r'Тип[:\s]+([^\n\r]+)',
            r'Модификация[:\s]+([^\n\r]+)',
        ]
        type_val = self._match_first(text, patterns)
        if type_val and not re.search(r'согласно|реестра|состав|автономных|перечень', type_val, re.IGNORECASE):
            return type_val
        return None

    def _extract_serial_number(self, text: str, file_name: str | None = None) -> str | None:
        """Extract serial number from text or file name."""
        # Compact serial token (letters, digits, dashes, slashes). Some serials have a single space inside.
        serial_tok = r'[A-Za-zА-Яа-яЁё0-9\-/]+(?:\s[A-Za-zА-Яа-яЁё0-9\-/]+)?'

        # Look for block "Заводской номер (номера): X" or "Заводской номер СИ: X" first
        match = re.search(
            r'заводской\s+номер\s*(?:\(номера\)|\s+СИ)?\s*[:\s]+(' + serial_tok + r')',
            text, re.IGNORECASE
        )
        serial = match.group(1).strip() if match else None

        if not serial:
            # Value on next line after placeholder (take only first token on that line)
            patterns = [
                r'заводской\s+номер\s*(?:\(номера\)|\s+СИ)?.*?\n\s*(' + serial_tok + r')',
                r'серийный\s+номер.*?\n\s*(' + serial_tok + r')',
                r'зав\.\s*№?[:\s]+(' + serial_tok + r')',
                r'№\s*заводской[:\s]+(' + serial_tok + r')',
            ]
            serial = self._match_first(text, patterns)

        if serial:
            # Clean up artifacts
            serial = re.sub(r'^\(номера\):\s*', '', serial)
            serial = re.sub(r'[();]', '', serial)
            serial = serial.strip()
            # Skip if it looks like a label
            if re.match(r'^(?:Год\s+выпуска|наименование|документ|методика|все\s+цифры)', serial, re.IGNORECASE):
                serial = None
            # Stop at label phrases that sometimes follow the real serial on the same line
            elif re.search(r'\b(?:Год(?:\s+выпуска)?|наименование|документ|методика|заводской|номер)', serial, re.IGNORECASE):
                serial = re.split(r'\b(?:Год(?:\s+выпуска)?|наименование|документ|методика|заводской|номер)', serial, flags=re.IGNORECASE)[0].strip()
                if len(serial) <= 1:
                    serial = None
            elif len(serial) <= 1 or len(serial) > 40:
                serial = None

        # If serial ends with a small integer (likely table row number leaked in), trim it
        if serial:
            parts = serial.split()
            if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) <= 2:
                serial = ' '.join(parts[:-1]).strip()
                if len(serial) <= 1:
                    serial = None

        # Fallback: extract from file name
        if not serial and file_name:
            # Match patterns like "№ 2062117", "№2062117", "2062117"
            match = re.search(r'№\s*([A-Za-zА-Яа-яЁё0-9\-/]+)', file_name)
            if match:
                serial = match.group(1).strip()
            else:
                # Try to extract number before extension
                match = re.search(r'([A-Za-zА-Яа-яЁё0-9\-/]+)\s*\([^)]*\)\.pdf', file_name)
                if match:
                    serial = match.group(1).strip()

        return serial

    def _extract_mit_number(self, text: str) -> str | None:
        """Extract MIT number (номер ОТ / госреестра) like '47279-11', '4041-93'.

        Strategy:
          1. Locate lines mentioning the registry ("реестр СИ"/"госреестр"/"номер по
             Гос. реестру") and look for a self-contained number in a small window
             (±3 lines) around them — covers both "номер under the label" and
             "номер between two labels" layouts. Numbers that are part of a method/
             equation of the form "N-N-YYYY" (e.g. МП 208-088-2018) are excluded.
          2. Fallback: whole-text search, longer numbers first, again skipping
             "N-N-YYYY" method numbers and (cid:N)-corrupted splits.
        """
        if not text:
            return None

        mit_token = r'(?<![-\d])\d{3,6}-\d{2,4}(?![-\d])'
        # Строки-маркеры секции реестра (наименование/подпись вокруг номера ОТ).
        registry_markers = (
            'реестр', 'реестра', 'реестре', 'реестру', 'реестры',
            'госреестр', 'гос. реестр', 'гос реестр',
            'регистрационный номер', 'в госреестре', 'в реестре', 'в гос. реестре',
        )

        lines = text.split('\n')
        for i, line in enumerate(lines):
            low = line.lower()
            if not any(mk in low for mk in registry_markers):
                continue
            start = max(0, i - 3)
            end = min(len(lines), i + 4)
            window = '\n'.join(lines[start:end])
            match = re.search(mit_token, window)
            if match:
                return match.group(0)

        # 2. Fallback — whole text, longer numbers first.
        patterns = [
            r'(?<![-\d])\d{5,6}-\d{2,4}(?![-\d])',
            r'(?<![-\d])\d{3,6}-\d{2,4}(?![-\d])',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(0)
        return None

    def _extract_manufacture_year(self, text: str) -> int | None:
        """Extract manufacture year."""
        patterns = [
            r'(?:\d+\.\s*)?Год\s+выпуска[:\s]+(\d{4})',
            r'(?:\d+\.\s*)?Дата\s+выпуска[:\s]+(\d{4})',
            r'(?:\d+\.\s*)?Год\s+изготовления[:\s]+(\d{4})',
            r'(?:\d+\.\s*)?Год\s+выпуска\D+(\d{4})',
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
            r'(?:\d+\.\s*)?Принадлеж(?:ащее|н(?:ость|ое|ность))[:\s]+([^\n\r]{3,100})',
            r'(?:\d+\.\s*)?Владелец\s+средства\s+измерений[:\s]+([^\n\r]{3,100})',
            r'(?:\d+\.\s*)?Владелец[:\s]+([^\n\r]{3,100})',
            r'(?:\d+\.\s*)?Организация[-\s]*владелец[:\s]+([^\n\r]{3,100})',
            r'(?:\d+\.\s*)?Организация[:\s]+([^\n\r]{3,100})',
        ]
        owner = self._match_first(text, patterns)
        if owner:
            # Clean: remove INN/KPP and trailing garbage
            owner = re.sub(r'\s*,?\s*ИНН\s*/?\s*КПП?\s*\d*', ' ', owner, flags=re.IGNORECASE)
            owner = re.sub(r'\s*,?\s*ИНН\s*\d{10,14}\s*', ' ', owner, flags=re.IGNORECASE)
            owner = re.sub(r'\s+\d{10,14}\s*', ' ', owner)
            owner = re.sub(r'["«»]', '', owner)
            # Stop at first comma or semicolon
            owner = re.split(r'[;,]\s*', owner)[0].strip()
            # Remove trailing numbered section headers (e.g. "3. Дата выпуска:")
            owner = re.sub(r'\s*\d+\.\s*[^\s]+.*$', '', owner).strip()
            owner = re.sub(r'\s+', ' ', owner).strip()
            if len(owner) > 3:
                return owner
        return None

    def _extract_verification_date(self, text: str) -> str | None:
        """Extract verification date in YYYY-MM-DD format."""
        # Look for "Дата поверки:" near the end of the document (after "Заключение:")
        # This avoids picking up certificate dates
        conclusion_match = re.search(r'Заключение:.*?(\n\n|\Z)', text, re.DOTALL)
        search_text = conclusion_match.group(0) if conclusion_match else text

        # Pattern: "Дата поверки: 01.12.2025 г."
        match = re.search(r'Дата\s+поверки[:\s]+(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})', search_text)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Fallback: "от 11.01.2024г." - but only in the last 1000 chars
        last_part = text[-1000:]
        match = re.search(r'от\s+(\d{1,2})[\.\-/](\d{1,2})[\.\-/](\d{4})', last_part)
        if match:
            day, month, year = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Pattern: "11 января 2024"
        match = re.search(r'(\d{1,2})\s+(\w+)\s+(\d{4})', last_part)
        if match:
            day, month_ru, year = match.groups()
            month = self.MONTH_MAP.get(month_ru.lower())
            if month:
                return f"{year}-{month}-{day.zfill(2)}"

        # Pattern: "2024-01-11"
        match = re.search(r'(\d{4})[\.\-/](\d{1,2})[\.\-/](\d{1,2})', last_part)
        if match:
            year, month, day = match.groups()
            return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        return None

    def _extract_verifier(self, text: str) -> str | None:
        """Extract verifier name.

        Handles both formats:
            Поверитель: Большаков С.Н.
            Кадыков П. Ю.
            Поверитель:
        """
        # Pattern A: name after "Поверитель:"
        match = re.search(r'поверитель[:\s]*\n\s*([^\n\r]+)', text, re.IGNORECASE)
        verifier = match.group(1).strip() if match else None
        if verifier and not re.search(r'подпись|фамилия|инициалы', verifier, re.IGNORECASE):
            verifier = normalize_verifier(verifier)
            if len(verifier) > 3:
                return verifier

        # Pattern B: name on line immediately BEFORE "Поверитель:"
        match = re.search(r'\n\s*([^\n\r]{5,40})\s*\n\s*Поверитель[:\s]*\s*$', text, re.IGNORECASE | re.MULTILINE)
        if match:
            verifier = match.group(1).strip()
            verifier = normalize_verifier(verifier)
            if len(verifier) > 3 and not re.search(r'подпись|фамилия|инициалы', verifier, re.IGNORECASE):
                return verifier

        # Fallback: inline pattern
        match = re.search(r'поверитель[:\s]+([^\n\r]+)', text, re.IGNORECASE)
        if match:
            verifier = match.group(1).strip()
            if not re.search(r'подпись|фамилия|инициалы', verifier, re.IGNORECASE):
                verifier = normalize_verifier(verifier)
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
        """Extract verification methodology (multi-line aware)."""
        # Pattern 1: multi-line capture until a clear boundary
        boundaries = r'(?:\n\s*(?:\d+\.\s*)?Средства\s+поверки|\n\s*(?:\d+\.\s*)?Условия\s+поверки|Технические\s+характеристики|Заключение|Дата\s+поверки)'
        labels = (
            r'(?:\d+\.\s*)?'
            r'(?:'
            r'Наименование\s+нормативного\s+документа\s+(?:(?:на\s+методику|по)\s+)?поверк(?:и|е)'
            r'|Нормативный\s+документ\s+на\s+методику\s+поверки'
            r'|Документ\s+на\s+методику\s+поверки'
            r'|Методика\s+поверки'
            r')'
        )
        match = re.search(
            labels + r'\s*[:\s]+'
            r'(.+?)' + boundaries,
            text,
            re.IGNORECASE | re.DOTALL,
        )
        if match:
            method = match.group(1)
            method = re.sub(r'\s+', ' ', method).strip()
            method = re.sub(r'наименование\s+и\s+номер\s+документа', ' ', method, flags=re.IGNORECASE)
            method = re.sub(r'"\s*Методика\s+поверки\s*"', '', method, flags=re.IGNORECASE)
            method = re.sub(r'«\s*', '«', method)
            method = re.sub(r'\s*»', '»', method)
            # Ensure matching quotes are closed
            open_q = method.count('«')
            close_q = method.count('»')
            if open_q > close_q:
                method += '»'
            method = re.sub(r'\s+', ' ', method).strip()
            method = re.sub(r'^[\s"«»\'„.,]+|[\s"«»\'„.,]+$', '', method)
            if self._is_valid_methodology(method):
                return method

        # Fallback: content inside «...» or "..." near "Методика поверки"
        match = re.search(r'Методика\s+поверки[^«"]*[«"]([^»"]{10,200})[»"]', text, re.IGNORECASE)
        if match:
            method = match.group(1).strip()
            if self._is_valid_methodology(method):
                return method

        # Fallback: find methodology reference codes like МИ ..., МП ..., ГОСТ ... near the phrase
        match = re.search(
            r'((?:МИ|МП|ГОСТ|РЭ)[-\s]*[\d\.\-/]+[^\n\r]{0,250}?(?:Методика\s+поверки|поверки))',
            text, re.IGNORECASE
        )
        if match:
            method = match.group(1).strip()
            # Trim after closing quote if present
            method = re.split(r'["»]', method)[0].strip()
            if self._is_valid_methodology(method):
                return method

        # Fallback to single-line patterns
        patterns = [
            r'Методика\s+поверки[:\s]+([^\n\r]+)',
            r'Методика[:\s]+([^\n\r]+)',
            r'по\s+методике[:\s]+([^\n\r]+)',
        ]
        method = self._match_first(text, patterns)
        if method:
            method = re.sub(r'"\s*Методика\s+поверки\s*"', '', method, flags=re.IGNORECASE)
            method = re.sub(r'^[\s"«»\'„.,]+|[\s"«»\'„.,]+$', '', method)
            method = method.strip()
            if self._is_valid_methodology(method):
                return method
        return None

    def _is_valid_methodology(self, value: str | None) -> bool:
        """Reject garbage methodology fragments."""
        if not value:
            return False
        v = value.strip()
        if len(v) < 8 or len(v) > 200:
            return False
        if v.lower() == 'поверки':
            return False
        # Must contain a document code if very long, or be short with digits
        has_code = bool(re.search(r'(?:М[ИП]|ГОСТ|РЭ|ГСИ)\s*[\d\.\-/]', v, re.IGNORECASE))
        # Also match manufacturer codes like КУВФ.405210.003 or КУВФ.405210.003 МП
        if not has_code:
            has_code = bool(re.search(r'[A-ZА-Яa-zа-я]{2,}\.\d+(?:\.\d+)+\s*(?:М[ИП])?\b', v))
        has_digit = bool(re.search(r'\d', v))
        if not has_code and not has_digit and not (
            15 <= len(v) <= 80
            and re.search(r'[а-яё]', v, re.IGNORECASE)
            and len(v.split()) >= 2
        ):
            return False
        if not has_code and len(v) > 80:
            return False
        # Reject section headers or template text fragments
        # Only apply when no official doc code is present (avoid rejecting
        # valid methodology names like "ГОСТ 8.461 ... Методы и средства поверки")
        if not has_code:
            garbage = [
                r'средства\s+поверки',
                r'условия\s+поверки',
                r'проведение\s+поверки',
                r'наименование\s+юридического',
                r'описание\s+средства',
                r'назначение\s+средства',
            ]
            v_lower = v.lower()
            if any(re.search(g, v_lower) for g in garbage):
                return False
        return True

    def _extract_result(self, text: str) -> str | None:
        """Extract verification result."""
        text_lower = text.lower()
        if 'пригод' in text_lower or 'соответств' in text_lower:
            return 'suitable'
        elif 'непригод' in text_lower or 'не соответств' in text_lower:
            return 'unsuitable'
        return None

    def _normalize_unit(self, unit: str) -> str | None:
        """Normalize a captured unit string to canonical form; return None if it doesn't look like a unit."""
        if not unit:
            return None
        u = unit.strip().lower()
        u = re.sub(r'[;,.\s]+$', '', u)
        aliases = {
            'кгс/см²': 'кгс/см²', 'кгс/см2': 'кгс/см²',
            'м³/ч': 'м³/ч', 'м3/ч': 'м³/ч',
            'мм': 'мм', 'см': 'см',
            'мпа': 'МПа', 'мПа': 'МПа', 'МПа': 'МПа',
            'кпа': 'кПа', 'кПа': 'кПа',
            'gpa': 'гПа', 'hpa': 'hPa',
            'па': 'Па', 'Па': 'Па',
            'bar': 'bar', 'бар': 'bar',
            '% нкпр': '% НКПР', '%нкпр': '% НКПР',
            '°c': '°C', '°с': '°C',
            '%': '%',
        }
        if u in aliases:
            return aliases[u]
        # Allow simple units not in alias list if they look like a unit (no long cyrillic words)
        if re.match(r'^[°a-zа-я0-9/³²%\-]+$', u, re.IGNORECASE) and len(u) <= 12:
            return unit.strip()
        return None

    def _extract_range(self, text: str, file_path: str | None = None) -> str | None:
        """Extract measurement range from text/table."""
        # 1. Prefer explicit range statement in the protocol text
        explicit_patterns = [
            # "Установленный диапазон измерений: ... (unit) X…+Y" (unit before numbers)
            (r'Установленный\s+диапазон\s+измерений[:\s]+'
             r'.{0,200}?\(?([°\w/³²]{1,10})\)?\s+([-+]?[\d\.,]+)\s*[\.…]{1,3}\s*\+?\s*([\d\.,]+)', 2, 3, 1),
            # "Установленный диапазон измерений: ... (unit) X-Y"
            (r'Установленный\s+диапазон\s+измерений[:\s]+'
             r'.{0,200}?\(?([°\w/³²]{1,10})\)?\s+([-+]?[\d\.,]+)\s*[-–—]\s*([\d\.,]+)', 2, 3, 1),
            # "Установленный диапазон измерений: ... от X до Y unit"
            (r'Установленный\s+диапазон\s+измерений[:\s]+'
             r'.{0,200}?от\s+([\d\.,\-]+)\s+до\s+([\d\.,\-]+)\s*([°\w/³²]{1,10})', 1, 2, 3),
            # "Установленный диапазон измерений: ... X…+Y unit" (ellipsis may be U+2026 or 2-3 dots)
            (r'Установленный\s+диапазон\s+измерений[:\s]+'
             r'.{0,200}?([\d\.,\-]+)\s*[\.…]{1,3}\s*\+?\s*([\d\.,\-]+)\s*\(?([°\w/³²]{1,10})\)?', 1, 2, 3),
            # "Установленный диапазон измерений: ... X-Y unit"
            (r'Установленный\s+диапазон\s+измерений[:\s]+'
             r'.{0,200}?([\d\.,\-]+)\s*[-–—]\s*([\d\.,\-]+)\s*([°\w/³²]{1,10})', 1, 2, 3),
            # "Диапазон измерений (X-Y) unit" when on same line as label
            (r'Диапазон\s+измерений\s*[:\s]*\(?([\d\.,]+)\s*[-–—]\s*([\d\.,]+)\)?\s*([\w/°³²%]{1,20})', 1, 2, 3),
            # Generic "от X до Y unit" within 200 chars of verification-related words
            (r'(?:поверки|измерения)\s*.{0,200}?от\s+([\d\.,]+)\s+до\s+([\d\.,]+)\s+([\w/°³²%]{1,20})', 1, 2, 3),
        ]
        for pattern, g1, g2, g3 in explicit_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                u = self._normalize_unit(match.group(g3))
                if u:
                    return f"({match.group(g1)}-{match.group(g2)}) {u}"

        # 2. Extract from pdfplumber tables if file_path is available
        if file_path and file_path.lower().endswith('.pdf'):
            try:
                table_range = self._extract_range_from_tables(file_path)
                if table_range:
                    return table_range
            except Exception:
                pass

        # 3. Fallback: try a strict "от X до Y unit" inside the verification section only
        table_match = re.search(
            r'(?:Определение|Проведение|Проведение\s+поверки)[^\n]*(?:\n[^\n]*){0,3}\n'
            r'(.{0,2500}?)(?:Заключение|Дата\s+поверки)',
            text, re.IGNORECASE | re.DOTALL
        )
        if table_match:
            table_text = table_match.group(1)
            m = re.search(r'от\s+([\d\.,]+)\s+до\s+([\d\.,]+)\s+([\w/°³²%]{1,20})', table_text, re.IGNORECASE)
            if m:
                u = self._normalize_unit(m.group(3))
                if u:
                    return f"({m.group(1)}-{m.group(2)}) {u}"

        return None

    def _extract_range_from_tables(self, file_path: str) -> str | None:
        """Use pdfplumber structured tables to determine measurement range."""
        import pdfplumber

        unit_aliases = {
            'кгс/см²': 'кгс/см²', 'кгс/см2': 'кгс/см²',
            'м³/ч': 'м³/ч', 'м3/ч': 'м³/ч',
            'мм': 'мм',
            'мпа': 'МПа', 'мПа': 'МПа', 'МПа': 'МПа',
            'кпа': 'кПа', 'кПа': 'кПа',
            'gpa': 'гПа', 'hpa': 'hPa',
            'па': 'Па', 'Па': 'Па',
            'bar': 'bar', 'бар': 'bar',
            '% нкпр': '% НКПР',
            '°c': '°C', '°с': '°C',
            '%': '%',
        }

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 3:
                        continue

                    # Flatten header/subheader rows
                    header_texts = []
                    for ridx in range(min(2, len(table))):
                        row_texts = [str(cell or '').replace('\n', ' ').strip().lower() for cell in table[ridx]]
                        header_texts.append(row_texts)

                    # Find candidate column index (measured/etalon column)
                    candidate_idx = None
                    for col in range(len(header_texts[0])):
                        col_text = ' '.join(
                            header_texts[r][col] if col < len(header_texts[r]) else ''
                            for r in range(len(header_texts))
                        )
                        if any(k in col_text for k in ['задаваемое', 'эталон', 'действительное', 'результат измерения']):
                            candidate_idx = col
                            break
                    if candidate_idx is None:
                        candidate_idx = 0

                    # Determine unit from candidate column header/subheader first
                    unit = None
                    for ridx in range(len(header_texts)):
                        if candidate_idx < len(header_texts[ridx]):
                            cell = header_texts[ridx][candidate_idx]
                            for alias, canonical in unit_aliases.items():
                                if alias.lower() in cell:
                                    unit = canonical
                                    break
                            if unit:
                                break
                    # Fallback: scan any header cell
                    if unit is None:
                        for ridx in range(len(header_texts)):
                            for cell in header_texts[ridx]:
                                for alias, canonical in unit_aliases.items():
                                    if alias.lower() in cell:
                                        unit = canonical
                                        break
                                if unit:
                                    break
                            if unit:
                                break

                    # Extra unit scan: look in first data rows for embedded units like "% НКПР"
                    if unit is None:
                        data_start = len(header_texts)
                        for ridx in range(data_start, min(data_start + 3, len(table))):
                            for raw_cell in table[ridx]:
                                c = str(raw_cell or '').replace('\n', ' ').strip().lower()
                                for alias, canonical in unit_aliases.items():
                                    if alias.lower() in c:
                                        unit = canonical
                                        break
                                if unit:
                                    break
                            if unit:
                                break

                    if unit is None:
                        continue

                    values = []
                    data_start = min(2, len(table))
                    for row in table[data_start:]:
                        if candidate_idx >= len(row):
                            continue
                        cell = str(row[candidate_idx] or '').strip()
                        if not cell:
                            continue
                        # Extract first number in cell
                        m = re.search(r'([\d\.,]+)', cell.replace(' ', '').replace('\n', ''))
                        if m:
                            try:
                                val = float(m.group(1).replace(',', '.'))
                                if 0 <= val < 1_000_000:
                                    values.append(val)
                            except ValueError:
                                continue

                    if len(values) >= 2:
                        # Filter out tiny outliers that are likely percentage errors
                        sorted_vals = sorted(values)
                        if len(sorted_vals) >= 3 and sorted_vals[1] > 0 and sorted_vals[0] / sorted_vals[1] < 0.05:
                            sorted_vals = sorted_vals[1:]
                        # Drop absurdly large max values (e.g. INN numbers leaked in)
                        if sorted_vals[-1] > 100_000:
                            sorted_vals = [v for v in sorted_vals if v <= 100_000]
                        if len(sorted_vals) < 2:
                            continue
                        min_val = sorted_vals[0]
                        max_val = sorted_vals[-1]
                        if max_val > min_val:
                            min_str = self._format_number(min_val)
                            max_str = self._format_number(max_val)
                            return f"({min_str}-{max_str}) {unit}"
        return None

    def _format_number(self, value: float) -> str:
        """Format float with comma decimal separator like original reports."""
        if value == int(value):
            return str(int(value))
        s = f"{value:.4f}".rstrip('0').replace('.', ',')
        return s

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
            "owner", "verification_method",
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
