"""AI extraction endpoint — delegates to AIExtractionService."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import settings
from app.api.v1.dependencies.auth import get_current_user
from app.services.ai_extraction_service import get_ai_extraction_service, DEFAULT_MODELS

router = APIRouter()


class AIExtractRequest(BaseModel):
    """Request body for AI extraction."""

    text: str
    system_prompt: str | None = None
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


@router.post("/extract", response_model=AIExtractResponse)
async def ai_extract(
    payload: AIExtractRequest,
    _: dict = Depends(get_current_user),
) -> AIExtractResponse:
    """Extract data from protocol text using AI with automatic fallback chain."""
    models = payload.fallback_models or DEFAULT_MODELS
    if payload.model and payload.model not in models:
        models = [payload.model] + models

    service = get_ai_extraction_service()
    result = await service.extract(
        text=payload.text,
        models=models,
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
    )

    return AIExtractResponse(
        content=result.get("content"),
        model=result.get("model"),
        status=result.get("status", "manual_review"),
        cost=result.get("cost", 0.0),
        attempts=result.get("attempts", 0),
        usage=result.get("usage"),
    )


@router.get("/models")
async def list_available_models(
    _: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """List available free models from OpenRouter."""
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
            "description": (m.get("description") or "")[:100],
        }
        for m in data.get("data", [])
        if ":free" in m.get("id", "")
    ]

    return {
        "free_models": free_models,
        "count": len(free_models),
        "configured_chain": DEFAULT_MODELS,
    }
