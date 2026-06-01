"""AI extraction service — extracts protocol data using OpenRouter with fallback chain."""

import json
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS = [
    "deepseek/deepseek-v4-flash:free",
    "inclusionai/ring-2.6-1t:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-4o-mini",
]

EXTRACTION_SYSTEM_PROMPT = (
    "You are a metrology lab assistant. Extract structured data from a "
    "calibration protocol in JSON format.\n"
    "Fields: protocol_number, device_name, device_type, serial_number, "
    "mit_number, manufacture_year, owner, verification_date (YYYY-MM-DD), "
    "verifier, temperature (number), humidity (number), pressure (number), "
    "pressure_units (kPa/mmHg), result (suitable/unsuitable), verification_method, measurement_range.\n"
    "If field is not found - null. Return ONLY JSON, no explanations."
)


class AIExtractionService:
    """Extract protocol data using AI models with automatic fallback."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _validate_extraction(self, content: str) -> tuple[bool, dict[str, Any] | None]:
        """Validate extracted JSON data."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
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
        is_valid = confidence >= 0.3 and score >= 0

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
        max_tokens: int = 1000,
        temperature: float = 0.1,
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
                response = await client.post(
                    f"{settings.OPENROUTER_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://metrocheck.ru",
                        "X-Title": "metroChek Protocol Control",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                            {"role": "user", "content": text[:8000]},
                        ],
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                result = response.json()

                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})

                if content is None:
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

            except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.warning("AI model %s failed: %s", model, e)
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
