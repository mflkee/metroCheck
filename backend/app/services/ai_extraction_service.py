"""AI extraction service — extracts protocol data using OpenRouter with fallback chain."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_MODELS = [
    "openrouter/free",                   # Auto-selected free model, usually reliable JSON
    "nvidia/nemotron-nano-12b-v2-vl:free",  # Free multimodal fallback
    "moonshotai/kimi-k2.6:free",         # Free (may be unavailable)
    "google/gemini-2.0-flash-001",       # Free (may be unavailable)
    "nvidia/nemotron-3-super-120b-a12b:free",  # Free fallback
]

# Vision-capable models for direct image processing
VISION_MODELS_CHEAP = [
    "openrouter/free",                   # Auto-selected free model
    "nvidia/nemotron-nano-12b-v2-vl:free",  # Free vision fallback
]

VISION_MODELS_PAID = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "anthropic/claude-3-haiku",
]


def _get_cache_dir() -> Path:
    """Return LLM cache directory. Override with METROCHECK_LLM_CACHE env var."""
    env = os.environ.get("METROCHECK_LLM_CACHE")
    if env:
        return Path(env)
    return Path.home() / ".cache" / "metrocheck" / "llm"


LLM_CACHE_DIR = _get_cache_dir()


def _cache_key(text: str, models: list[str] | None, max_tokens: int) -> str:
    """Build deterministic cache key."""
    payload = json.dumps({
        "text": text,
        "models": models or DEFAULT_MODELS,
        "max_tokens": max_tokens,
    }, ensure_ascii=True, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_from_cache(key: str) -> dict[str, Any] | None:
    """Load cached LLM result if present."""
    if os.environ.get("METROCHECK_DISABLE_LLM_CACHE"):
        return None
    cache_file = LLM_CACHE_DIR / f"{key}.json"
    try:
        if cache_file.exists():
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("LLM cache read failed: %s", e)
    return None


def _save_to_cache(key: str, result: dict[str, Any]) -> None:
    """Save LLM result to cache."""
    if os.environ.get("METROCHECK_DISABLE_LLM_CACHE"):
        return
    try:
        LLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = LLM_CACHE_DIR / f"{key}.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.debug("LLM cache write failed: %s", e)

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
        if not settings.OPENROUTER_API_KEY:
            return {
                "content": None,
                "model": None,
                "status": "manual_review",
                "cost": 0.0,
                "attempts": 0,
                "usage": None,
            }

        model_chain = models or DEFAULT_MODELS

        cache_key = _cache_key(text, models, max_tokens)
        cached = _load_from_cache(cache_key)
        if cached is not None:
            logger.debug("LLM cache hit for text extraction")
            return cached

        client = await self._get_client()

        last_error: Exception | None = None
        for attempt, model in enumerate(model_chain, 1):
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

            retries = 0
            max_retries = 3
            while retries <= max_retries:
                try:
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
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and retries < max_retries:
                        wait = min(2 ** retries * 5 + (hash(model) % 5), 60)
                        logger.warning("Model %s rate limited (429), waiting %ss...", model, wait)
                        await asyncio.sleep(wait)
                        retries += 1
                        continue
                    logger.warning("AI model %s failed: %s", model, e)
                    last_error = e
                    break
                except Exception as e:
                    logger.warning("AI model %s failed: %s", model, e)
                    last_error = e
                    break
            else:
                # All retries exhausted for this model
                continue

            if last_error is not None and isinstance(last_error, Exception):
                # Don't reset last_error here; we want to try next model
                pass

            try:
                choices = result.get("choices") or []
                if not choices:
                    logger.warning("Model %s returned no choices", model)
                    continue
                message = choices[0].get("message") or {}
                content = message.get("content")
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
                    result_to_cache = {
                        "content": data,
                        "model": model,
                        "status": "success",
                        "cost": cost,
                        "attempts": attempt,
                        "usage": usage,
                    }
                    _save_to_cache(cache_key, result_to_cache)
                    return result_to_cache

                # Log why validation failed for debugging
                logger.debug("Model %s response failed validation: %s", model, content[:200])

            except (KeyError, TypeError, AttributeError) as e:
                logger.warning("AI model %s response parsing failed: %s", model, e)
                continue

        result_to_cache = {
            "content": None,
            "model": None,
            "status": "manual_review",
            "cost": 0.0,
            "attempts": len(model_chain),
            "usage": None,
        }
        _save_to_cache(cache_key, result_to_cache)
        return result_to_cache

    async def extract_from_image(
        self,
        image_path: str,
        hint_text: str = "",
        models: list[str] | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Extract protocol data from an image using vision-capable models.

        Encodes the image as base64 and sends a vision request.

        Args:
            image_path: Path to JPG/PNG image file
            hint_text: Optional OCR pre-result text to include as context hint
            models: Vision model chain, defaults to free + paid
            max_tokens: Max completion tokens
            temperature: Model temperature
        """
        # Read and encode image
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
        except OSError as e:
            logger.error("Cannot read image %s: %s", image_path, e)
            return {
                "content": None,
                "model": None,
                "status": "manual_review",
                "cost": 0.0,
                "attempts": 0,
            }

        ext = os.path.splitext(image_path)[1].lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        mime_type = mime_map.get(ext, "image/jpeg")

        model_chain = models or (VISION_MODELS_CHEAP + VISION_MODELS_PAID)
        if not settings.OPENROUTER_API_KEY:
            return {
                "content": None,
                "model": None,
                "status": "manual_review",
                "cost": 0.0,
                "attempts": 0,
            }

        # Cache by image content + hint + models
        cache_key = _cache_key(image_data[:1000] + hint_text, models, max_tokens)
        cached = _load_from_cache(cache_key)
        if cached is not None:
            logger.debug("LLM cache hit for image extraction")
            return cached

        client = await self._get_client()

        # Build system prompt with optional OCR hint
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        user_content: list[dict[str, Any]] = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{image_data}",
                    "detail": "high",
                },
            },
        ]

        if hint_text:
            user_content.insert(0, {
                "type": "text",
                "text": f"OCR предварительный результат (может содержать ошибки):\n{hint_text[:2000]}",
            })

        for attempt, model in enumerate(model_chain, 1):
            payload: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            if model.startswith("openai/"):
                payload["response_format"] = {"type": "json_object"}

            retries = 0
            max_retries = 3
            while retries <= max_retries:
                try:
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
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    result = response.json()
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429 and retries < max_retries:
                        wait = min(2 ** retries * 5 + (hash(model) % 5), 60)
                        logger.warning("Vision model %s rate limited (429), waiting %ss...", model, wait)
                        await asyncio.sleep(wait)
                        retries += 1
                        continue
                    logger.warning("Vision model %s failed: %s", model, e)
                    break
                except Exception as e:
                    logger.warning("Vision model %s failed: %s", model, e)
                    break
            else:
                continue

            try:
                choices = result.get("choices") or []
                if not choices:
                    logger.warning("Vision model %s returned no choices", model)
                    continue
                message = choices[0].get("message") or {}
                content = message.get("content")
                usage = result.get("usage", {})

                if content is None:
                    continue

                completion_tokens = usage.get("completion_tokens", 0)
                if completion_tokens > 800:
                    logger.warning("Vision model %s generated too many tokens (%s)", model, completion_tokens)
                    continue

                is_valid, data = self._validate_extraction(content)

                if is_valid:
                    cost = self._calculate_cost(usage, model)
                    result_to_cache = {
                        "content": data,
                        "model": model,
                        "status": "success",
                        "cost": cost,
                        "attempts": attempt,
                        "usage": usage,
                    }
                    _save_to_cache(cache_key, result_to_cache)
                    return result_to_cache

            except (KeyError, TypeError, AttributeError) as e:
                logger.warning("Vision model %s response parsing failed: %s", model, e)
                continue

        result_to_cache = {
            "content": None,
            "model": None,
            "status": "manual_review",
            "cost": 0.0,
            "attempts": len(model_chain),
            "usage": None,
        }
        _save_to_cache(cache_key, result_to_cache)
        return result_to_cache


_extraction_service: AIExtractionService | None = None


def get_ai_extraction_service() -> AIExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = AIExtractionService()
    return _extraction_service
