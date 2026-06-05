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
    "google/gemini-2.0-flash-001",     # Free (no rate limit on OpenRouter)
    "nvidia/nemotron-3-super-120b-a12b:free",  # Free fallback
]

EXTRACTION_SYSTEM_PROMPT = (
    "Извлеки данные из протокола поверки СИ РФ. Верни ТОЛЬКО JSON.\n\n"
    "ПРАВИЛА:\n"
    "1. Только JSON, без markdown и комментариев\n"
    "2. null если поле не найдено\n"
    "3. Дата: YYYY-MM-DD\n"
    "4. result: 'suitable' или 'unsuitable'\n\n"
    "ПОЛЯ (ищи по ключевым словам):\n"
    "- protocol_number: № протокола\n"
    "- device_name: Наименование СИ\n"
    "- device_type: Тип/модификация\n"
    "- serial_number: Заводской №/серийный №\n"
    "- mit_number: № в госреестре (формат 12345-67)\n"
    "- manufacture_year: Год выпуска\n"
    "- owner: Владелец\n"
    "- verification_date: Дата поверки\n"
    "- verifier: Поверитель (ФИО)\n"
    "- temperature, humidity, pressure: условия поверки\n"
    "- result: пригодно/непригодно\n"
    "- verification_method: Методика/документ\n"
    "- measurement_range: Диапазон (например 'от 4 до 400 м³/ч')\n\n"
    "Пример:\n"
    '{"protocol_number":"01/001/24","device_name":"счетчик газа",'
    '"device_type":"КТМ600 РУС","serial_number":"21148561",'
    '"mit_number":"62301-15","manufacture_year":2021,'
    '"owner":"ООО ИНК","verification_date":"2024-01-11",'
    '"verifier":"Чупин А.А.","temperature":22.8,"humidity":39.0,'
    '"pressure":100.9,"pressure_units":"кПа","result":"suitable",'
    '"verification_method":"МП 0302-13-2015","measurement_range":"(4-400) м³/ч"}'
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

            except (TimeoutError, httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, AttributeError) as e:
                is_429 = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
                if is_429:
                    logger.warning("AI model %s rate limited (429), waiting 15s...", model)
                    await asyncio.sleep(15.0)
                else:
                    logger.warning("AI model %s failed: %s", model, e)
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
