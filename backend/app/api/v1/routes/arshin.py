"""ARSHIN (ФГИС Росаккредитации) integration endpoints."""

import asyncio
from typing import Any, Optional

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
    await tm.update(task_id, status="waiting_token", progress="Waiting for ARSHIN token via shared file (Synology Drive)...")
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


# === Scheduler Control Endpoints ===

class SchedulerModeRequest(BaseModel):
    mode: str  # "manual" or "auto"


class SchedulerSettingsRequest(BaseModel):
    mode: Optional[str] = None
    auto_time: Optional[str] = None  # "HH:MM"
    auto_day: Optional[int] = None   # 1-31
    month_offset: Optional[int] = None  # -12 to 0


@router.get("/scheduler/status")
async def scheduler_status(
    x_api_key: str = Header(...),
) -> dict:
    """Get scheduler status with all settings."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    import os
    import json
    state_file = os.environ.get("SCHEDULER_STATE", "/tmp/scheduler_state.json")
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
    else:
        state = {
            "mode": "manual",
            "auto_time": "09:00",
            "auto_day": 1,
            "month_offset": -1,
        }
    
    # Calculate example
    from datetime import datetime
    now = datetime.utcnow()
    offset = state.get("month_offset", -1)
    target = now.month + offset
    year = now.year
    while target <= 0:
        target += 12
        year -= 1
    while target > 12:
        target -= 12
        year += 1
    
    return {
        "status": "ok",
        "scheduler": {
            **state,
            "example": f"If today is {now.strftime('%d.%m.%Y')}, will check: {target:02d}.{year}",
        },
    }


@router.post("/scheduler/mode")
async def set_scheduler_mode(
    payload: SchedulerModeRequest,
    x_api_key: str = Header(...),
) -> dict:
    """Set scheduler mode: manual or auto."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    if payload.mode not in ("manual", "auto"):
        raise HTTPException(status_code=400, detail="Mode must be 'manual' or 'auto'")
    
    import os
    import json
    state_file = os.environ.get("SCHEDULER_STATE", "/tmp/scheduler_state.json")
    state = {}
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
    state["mode"] = payload.mode
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
    
    return {
        "status": "ok",
        "mode": payload.mode,
        "message": f"Scheduler switched to {payload.mode} mode",
    }


@router.post("/scheduler/settings")
async def update_scheduler_settings(
    payload: SchedulerSettingsRequest,
    x_api_key: str = Header(...),
) -> dict:
    """Update scheduler settings: time, day, month offset.
    
    Example: auto_day=10, month_offset=-2
    → On 10th of each month, check month-2 (e.g., July→May)
    """
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    import os
    import json
    state_file = os.environ.get("SCHEDULER_STATE", "/tmp/scheduler_state.json")
    state = {}
    if os.path.exists(state_file):
        with open(state_file) as f:
            state = json.load(f)
    
    updated = {}
    
    if payload.mode is not None:
        if payload.mode not in ("manual", "auto"):
            raise HTTPException(status_code=400, detail="Mode must be 'manual' or 'auto'")
        state["mode"] = payload.mode
        updated["mode"] = payload.mode
    
    if payload.auto_time is not None:
        try:
            hour, minute = map(int, payload.auto_time.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            state["auto_time"] = payload.auto_time
            updated["auto_time"] = payload.auto_time
        except ValueError:
            raise HTTPException(status_code=400, detail="Time must be HH:MM format")
    
    if payload.auto_day is not None:
        if not (1 <= payload.auto_day <= 31):
            raise HTTPException(status_code=400, detail="Day must be 1-31")
        state["auto_day"] = payload.auto_day
        updated["auto_day"] = payload.auto_day
    
    if payload.month_offset is not None:
        if not (-12 <= payload.month_offset <= 0):
            raise HTTPException(status_code=400, detail="Month offset must be -12 to 0")
        state["month_offset"] = payload.month_offset
        updated["month_offset"] = payload.month_offset
    
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)
    
    # Calculate example
    from datetime import datetime
    now = datetime.utcnow()
    offset = state.get("month_offset", -1)
    target = now.month + offset
    year = now.year
    while target <= 0:
        target += 12
        year -= 1
    
    return {
        "status": "ok",
        "updated": updated,
        "current_settings": state,
        "example": f"Next run: day {state.get('auto_day', 1)} at {state.get('auto_time', '09:00')} → will check {target:02d}.{year}",
    }


@router.post("/run-check")
async def run_check_manual(
    payload: FetchLKDetailsRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger a check for specific month.
    
    Works in both manual and auto modes.
    """
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.services.job_queue_service import JobQueueService
    
    queue = JobQueueService(db)
    job = await queue.enqueue_manual(payload.year, payload.month, triggered_by="user")
    
    return {
        "status": "ok",
        "job_id": job.id,
        "year": payload.year,
        "month": payload.month,
        "message": f"Check queued for {payload.month:02d}.{payload.year}",
    }
