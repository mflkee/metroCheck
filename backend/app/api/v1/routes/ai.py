"""AI extraction proxy endpoint with fallback chain."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
import httpx

from app.core.config import settings

router = APIRouter()

# Default fallback chain: free models first, paid gpt-4o-mini last
DEFAULT_MODELS = [
    "deepseek/deepseek-v4-flash:free",
    "inclusionai/ring-2.6-1t:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "openai/gpt-4o-mini",
]


class AIExtractRequest(BaseModel):
    """Request body for AI extraction."""

    text: str
    system_prompt: str
    model: str | None = None
    fallback_models: list[str] | None = None
    max_tokens: int = 1000
    temperature: float = 0.1


class AIExtractResponse(BaseModel):
    """Response from AI extraction."""

    content: dict[str, Any] | None
    model: str | None
    status: str
    cost: float
    attempts: int
    usage: dict[str, Any] | None = None


def _validate_extraction(content: str) -> tuple[bool, dict[str, Any] | None]:
    """Validate extracted data. Returns (is_valid, data)."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False, None

    if not isinstance(data, dict):
        return False, None

    # Required fields for confidence scoring
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

    # Penalize anomalous values (handle string units like "20°C", "55%")
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


def _calculate_cost(usage: dict[str, Any], model: str) -> float:
    """Calculate cost in USD."""
    if ":free" in model:
        return 0.0

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    if "gpt-4o-mini" in model:
        return prompt_tokens * 0.15e-6 + completion_tokens * 0.6e-6

    return 0.0


@router.post("/extract", response_model=AIExtractResponse)
async def ai_extract(
    payload: AIExtractRequest,
    x_api_key: str = Header(...),
) -> AIExtractResponse:
    """Extract data from protocol text using AI with automatic fallback chain.

    Fallback: NN1 (gemma-4-31b) -> NN2 (qwen3-next) -> NN3 (gpt-oss-120b) -> NN4 (gpt-4o-mini)
    """
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    models = payload.fallback_models or DEFAULT_MODELS
    if payload.model and payload.model not in models:
        models = [payload.model] + models

    system_prompt = payload.system_prompt
    if not system_prompt:
        system_prompt = (
            "You are a metrology lab assistant. Extract structured data from a "
            "calibration protocol in JSON format.\n"
            "Fields: protocol_number, device_name, device_type, serial_number, "
            "mit_number, manufacture_year, owner, verification_date (YYYY-MM-DD), "
            "verifier, temperature (number), humidity (number), pressure (number), "
            "pressure_units (kPa/mmHg), result (suitable/unsuitable), verification_method.\n"
            "If field is not found - null. Return ONLY JSON, no explanations."
        )

    async with httpx.AsyncClient(timeout=120.0) as client:
        for attempt, model in enumerate(models, 1):
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
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": payload.text},
                        ],
                        "max_tokens": payload.max_tokens,
                        "temperature": payload.temperature,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                result = response.json()

                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})

                if content is None:
                    continue

                is_valid, data = _validate_extraction(content)

                if is_valid:
                    cost = _calculate_cost(usage, model)
                    return AIExtractResponse(
                        content=data,
                        model=model,
                        status="success",
                        cost=cost,
                        attempts=attempt,
                        usage=usage,
                    )

                # Not valid - try next model
                continue

            except (httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, AttributeError) as e:
                continue

    # All models failed
    return AIExtractResponse(
        content=None,
        model=None,
        status="manual_review",
        cost=0.0,
        attempts=len(models),
        usage=None,
    )


@router.get("/models")
async def list_available_models(x_api_key: str = Header(...)) -> dict[str, Any]:
    """List available free models from OpenRouter."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            },
        )
        response.raise_for_status()
        data = response.json()

    free_models = [
        {
            "id": m["id"],
            "context_length": m.get("context_length"),
            "description": m.get("description", "")[:100],
        }
        for m in data.get("data", [])
        if ":free" in m.get("id", "")
    ]

    return {
        "free_models": free_models,
        "count": len(free_models),
        "configured_chain": DEFAULT_MODELS,
    }
