"""AI extraction service — extracts protocol data using OpenRouter with fallback chain."""

import asyncio
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS = [
    "moonshotai/kimi-k2.6:free",       # Free, strong at Russian text
    "nvidia/nemotron-3-super-120b-a12b:free",  # Free fallback
    "openai/gpt-4o-mini",              # Paid fallback
]

EXTRACTION_SYSTEM_PROMPT = (
    "Ты — специалист по извлечению данных из протоколов поверки средств измерений (СИ) РФ. "
    "Извлеки ВСЕ возможные поля из текста протокола и верни ТОЛЬКО JSON-объект.\n\n"
    "=== СТРОГИЕ ПРАВИЛА ===\n"
    "1. Верни ТОЛЬКО JSON — без markdown, без объяснений, без комментариев\n"
    "2. Если поле не найдено в тексте — используй null (не пустую строку)\n"
    "3. НЕ повторяй исходный текст\n"
    "4. НЕ добавляй поля, которых нет в списке ниже\n"
    "5. Дата verification_date ТОЛЬКО в формате YYYY-MM-DD\n"
    "6. Результат result ТОЛЬКО 'suitable' (пригодно) или 'unsuitable' (непригодно)\n"
    "7. Все строковые значения бери из текста протокола как есть, без изменений\n\n"
    "=== ГДЕ ИСКАТЬ ПОЛЯ В ПРОТОКОЛЕ ===\n"
    "- protocol_number: после 'ПРОТОКОЛ ПОВЕРКИ №' (например '01/001/24')\n"
    "- device_name: после 'Наименование средства измерений:' (например 'счетчик газа')\n"
    "- device_type: после 'Тип, модификация средства измерений:' (например 'КТМ600 РУС')\n"
    "- serial_number: после 'Заводской номер' или '№' устройства (например '21148561')\n"
    "- mit_number: номер по Государственному реестру СИ РФ, обычно после 'реестру СИ РФ' (например '62301-15')\n"
    "- manufacture_year: после 'Год выпуска:' или 'Год изготовления:' (число, например 2021)\n"
    "- owner: после 'Принадлежит:', 'Владелец:' или 'Принадлежащее' (например 'ООО ИНК')\n"
    "- verification_date: после 'Дата поверки:' или 'от' у протокола (YYYY-MM-DD)\n"
    "- verifier: ФИО поверителя, после 'Поверитель:' (например 'Чупин А.А.')\n"
    "- temperature: после 'Температура окружающей среды' (число с °C, например 22.8)\n"
    "- humidity: после 'Относительная влажность' (число с %, например 39.0)\n"
    "- pressure: после 'Атмосферное давление' (число, например 100.9)\n"
    "- pressure_units: единицы давления (обычно 'кПа' или 'kPa')\n"
    "- result: после 'Результат поверки' — 'пригодно'→'suitable', 'непригодно'→'unsuitable'\n"
    "- verification_method: после 'Методика поверки' или 'Метод поверки' (например 'МП 0302-13-2015')\n"
    "- measurement_range: после 'Диапазон измерений' или пределы (например '(4-400) м³/ч')\n\n"
    "=== ПРИМЕР ===\n"
    '{"protocol_number":"01/001/24","device_name":"счетчик газа",'
    '"device_type":"КТМ600 РУС","serial_number":"21148561",'
    '"mit_number":"62301-15","manufacture_year":2021,'
    '"owner":"ООО ИНК","verification_date":"2024-01-11",'
    '"verifier":"Чупин А.А.","temperature":22.8,"humidity":39.0,'
    '"pressure":100.9,"pressure_units":"кПа","result":"suitable",'
    '"verification_method":"МП 0302-13-2015","measurement_range":"(4-400) м³/ч"}\n\n'
    "=== ПОЛЯ ДЛЯ ИЗВЛЕЧЕНИЯ ===\n"
    "protocol_number, device_name, device_type, serial_number, "
    "mit_number, manufacture_year, owner, verification_date, verifier, "
    "temperature, humidity, pressure, pressure_units, result, "
    "verification_method, measurement_range\n\n"
    "ВАЖНО: Извлеки МАКСИМУМ полей из текста. Если значение не найдено — используй null."
)


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """Try to extract JSON from markdown code blocks or raw text."""
    if not text:
        return None

    # 1. Try direct JSON parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Try markdown code block ```json {...} ```
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Try to find first { ... } pair
    match = re.search(r'(\{.*\})', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None


class AIExtractionService:
    """Extract protocol data using AI models with automatic fallback."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _validate_extraction(self, content: str) -> tuple[bool, dict[str, Any] | None]:
        """Validate extracted JSON data."""
        data = _extract_json_from_text(content)
        if data is None:
            return False, None

        if not isinstance(data, dict):
            return False, None

        required = [
            "protocol_number",
            "serial_number",
            "device_name",
            "verification_date",
            "verifier",
            "temperature",
            "humidity",
            "pressure",
        ]

        score = 0
        for field in required:
            if data.get(field) is not None:
                score += 1

        temp = data.get("temperature")
        if temp is not None:
            try:
                temp_num = float(str(temp).replace(",", ".").split()[0].replace("°C", "").replace("C", ""))
                if temp_num < -50 or temp_num > 60:
                    score -= 2
            except (ValueError, TypeError):
                pass

        humidity = data.get("humidity")
        if humidity is not None:
            try:
                hum_num = float(str(humidity).replace("%", "").replace(",", ".").split()[0])
                if hum_num < 0 or hum_num > 100:
                    score -= 2
            except (ValueError, TypeError):
                pass

        confidence = max(0, score / len(required))
        is_valid = confidence >= 0.2  # Lowered from 0.3

        return is_valid, data

    def _calculate_cost(self, usage: dict[str, Any], model: str) -> float:
        """Calculate cost in USD."""
        if ":free" in model:
            return 0.0

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        if "gpt-4o-mini" in model:
            return prompt_tokens * 0.15e-6 + completion_tokens * 0.6e-6

        return 0.0

    async def extract(
        self,
        text: str,
        models: list[str] | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Extract protocol data from text using AI.

        Returns dict with keys:
            content: dict of extracted fields or None
            model: model that succeeded
            status: "success", "manual_review"
            cost: float
            attempts: int
        """
        model_chain = models or DEFAULT_MODELS
        client = await self._get_client()

        for attempt, model in enumerate(model_chain, 1):
            try:
                payload: dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {"role": "user", "content": text[:8000]},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }

                # Only OpenAI models support json_object response format reliably
                if model.startswith("openai/"):
                    payload["response_format"] = {"type": "json_object"}

                response = await asyncio.wait_for(
                    client.post(
                        f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://metrocheck.ru",
                            "X-Title": "metroChek Protocol Control",
                        },
                        json=payload,
                    ),
                    timeout=35.0,
                )
                response.raise_for_status()
                result = response.json()

                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})

                if content is None:
                    continue

                # Detect model "hallucination" — too many tokens means not JSON
                completion_tokens = usage.get("completion_tokens", 0)
                if completion_tokens > 800:
                    logger.warning("Model %s generated too many tokens (%s), likely not JSON", model, completion_tokens)
                    continue

                is_valid, data = self._validate_extraction(content)

                if is_valid:
                    cost = self._calculate_cost(usage, model)
                    return {
                        "content": data,
                        "model": model,
                        "status": "success",
                        "cost": cost,
                        "attempts": attempt,
                        "usage": usage,
                    }

                # Log why validation failed for debugging
                logger.debug("Model %s response failed validation: %s", model, content[:200])

            except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, AttributeError, asyncio.TimeoutError) as e:
                logger.warning("AI model %s failed: %s", model, e)
                # Rate limit cooldown between models
                await asyncio.sleep(1.0)
                continue

        return {
            "content": None,
            "model": None,
            "status": "manual_review",
            "cost": 0.0,
            "attempts": len(model_chain),
            "usage": None,
        }


_extraction_service: AIExtractionService | None = None


def get_ai_extraction_service() -> AIExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = AIExtractionService()
    return _extraction_service
