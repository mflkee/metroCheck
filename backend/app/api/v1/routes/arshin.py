"""ARSHIN (ФГИС Росаккредитации) integration endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.integrations.arshin_client import ArshinClient
from app.services.arshin_service import ArshinService
from app.services.task_manager import get_task_manager

router = APIRouter()


class FetchCalibrationsRequest(BaseModel):
    year: int
    month: int
    org_title: str = 'ООО "МКАИР"'


class FetchLKDetailsRequest(BaseModel):
    year: int
    month: int


@router.get("/status")
async def arshin_status() -> dict:
    """Check ARSHIN API availability."""
    client = ArshinClient()
    try:
        import asyncio
        count = await client.get_calibration_count(
            'ООО "МКАИР"',
            __import__('datetime').date(2025, 1, 1),
            __import__('datetime').date(2025, 1, 31),
        )
        return {"status": "ok", "arshin": "available", "sample_count": count}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"ARSHIN unavailable: {e}")


@router.get("/token-status")
async def token_status(
    x_api_key: str = Header(...),
) -> dict:
    """Check ARSHIN Bearer token availability."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    client = ArshinClient()
    token = client.bearer_token
    if token:
        return {"status": "ok", "expires_in": int(client._token_expires - __import__("time").time())}
    return {"status": "expired", "expires_in": 0}


@router.post("/refresh-token", status_code=202)
async def refresh_token(
    x_api_key: str = Header(...),
) -> dict:
    """Start token refresh in background. Returns task_id for polling."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    tm = get_task_manager()
    task_id = await tm.create("token_refresh")
    await tm.update(task_id, status="waiting_token", progress="Requesting ARSHIN token via Netbird...")
    asyncio.ensure_future(_refresh_token_task(task_id))
    return {"task_id": task_id, "status": "accepted"}


async def _refresh_token_task(task_id: str) -> None:
    """Background task: polls token-agent until token arrives."""
    tm = get_task_manager()
    client = ArshinClient()
    try:
        token = await client._request_new_token()
        await tm.update(
            task_id,
            status="completed",
            result={"token_prefix": token[:20] + "..."},
            progress="Token obtained",
        )
    except asyncio.CancelledError:
        await tm.update(task_id, status="failed", error="Cancelled")
    except Exception as e:
        await tm.update(task_id, status="failed", error=str(e))


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    x_api_key: str = Header(...),
) -> dict:
    """Get status of any async task (token refresh, etc.)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    tm = get_task_manager()
    task = await tm.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    resp: dict[str, Any] = {
        "task_id": task["id"],
        "status": task["status"],
        "progress": task["progress"],
    }
    if task["result"]:
        resp["result"] = task["result"]
    if task["error"]:
        resp["error"] = task["error"]
    return resp


@router.post("/fetch-lk-async", status_code=202)
async def fetch_lk_details_async(
    payload: FetchLKDetailsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch LK details with async token waiting. Returns task_id."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    tm = get_task_manager()
    task_id = await tm.create(f"lk_details_{payload.year}_{payload.month}")
    await tm.update(task_id, status="pending", progress="Task created")
    asyncio.ensure_future(_fetch_lk_task(task_id, payload.year, payload.month))
    return {"task_id": task_id, "status": "accepted"}


async def _fetch_lk_task(task_id: str, year: int, month: int) -> None:
    """Background: fetch LK details, wait for token if needed."""
    from app.core.database import AsyncSessionLocal
    from app.integrations.arshin_client import ArshinClient

    tm = get_task_manager()
    client = ArshinClient()

    try:
        token = client.bearer_token
        if not token:
            await tm.update(
                task_id,
                status="waiting_token",
                progress="ARSHIN token expired. Waiting for Зонов to login via Госуслуги...",
            )
            token = await client._request_new_token()
            await tm.update(
                task_id,
                status="running",
                progress="Token obtained, fetching LK details...",
            )

        async with AsyncSessionLocal() as session:
            service = ArshinService(session)
            await tm.update(
                task_id,
                status="running",
                progress=f"Fetching LK details for {year}-{month:02d}...",
            )
            result = await service.fetch_lk_details(year, month)
            await tm.update(
                task_id,
                status="completed",
                result=result,
                progress="LK details fetched",
            )
    except asyncio.CancelledError:
        await tm.update(task_id, status="failed", error="Task cancelled")
    except Exception as e:
        await tm.update(task_id, status="failed", error=str(e))


async def _fetch_data2_task(task_id: str, year: int, month: int) -> None:
    """Background: fetch LK data2, wait for token if needed."""
    from app.core.database import AsyncSessionLocal
    from app.integrations.arshin_client import ArshinClient

    tm = get_task_manager()
    client = ArshinClient()

    try:
        token = client.bearer_token
        if not token:
            await tm.update(
                task_id,
                status="waiting_token",
                progress="ARSHIN token expired. Waiting for Зонов to login via Госуслуги...",
            )
            token = await client._request_new_token()
            await tm.update(
                task_id,
                status="running",
                progress="Token obtained, fetching LK data2...",
            )

        async with AsyncSessionLocal() as session:
            service = ArshinService(session)
            await tm.update(
                task_id,
                status="running",
                progress=f"Fetching LK data2 for {year}-{month:02d}...",
            )
            result = await service.fetch_lk_data2(year, month)
            await tm.update(
                task_id,
                status="completed",
                result=result,
                progress="LK data2 fetched",
            )
    except asyncio.CancelledError:
        await tm.update(task_id, status="failed", error="Task cancelled")
    except Exception as e:
        await tm.update(task_id, status="failed", error=str(e))


@router.post("/fetch-data2-async", status_code=202)
async def fetch_lk_data2_async(
    payload: FetchLKDetailsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch extended LK data2 with async token waiting. Returns task_id."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    tm = get_task_manager()
    task_id = await tm.create(f"lk_data2_{payload.year}_{payload.month}")
    await tm.update(task_id, status="pending", progress="Task created")
    asyncio.ensure_future(_fetch_data2_task(task_id, payload.year, payload.month))
    return {"task_id": task_id, "status": "accepted"}


@router.post("/fetch-calibrations")
async def fetch_calibrations(
    payload: FetchCalibrationsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch calibration list from ARSHIN public API and save to DB."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = ArshinService(db)
    result = await service.fetch_and_save_calibrations(payload.year, payload.month)
    return result


@router.post("/fetch-lk-details")
async def fetch_lk_details(
    payload: FetchLKDetailsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch details from ARSHIN LK (requires Bearer token)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if not settings.ARSHIN_BEARER_TOKEN:
        raise HTTPException(status_code=400, detail="ARSHIN_BEARER_TOKEN not configured")

    service = ArshinService(db)
    result = await service.fetch_lk_details(payload.year, payload.month)
    return result


@router.post("/fetch-lk-data2")
async def fetch_lk_data2(
    payload: FetchLKDetailsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch extended data from ARSHIN LK."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if not settings.ARSHIN_BEARER_TOKEN:
        raise HTTPException(status_code=400, detail="ARSHIN_BEARER_TOKEN not configured")

    service = ArshinService(db)
    result = await service.fetch_lk_data2(payload.year, payload.month)
    return result
