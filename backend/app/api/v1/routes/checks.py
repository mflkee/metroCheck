"""Check execution endpoints."""

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.check_service import CheckService
from app.services.task_manager import get_task_manager

router = APIRouter()


class RunCheckRequest(BaseModel):
    year: int
    month: int


@router.post("/run")
async def run_checks(
    payload: RunCheckRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a check run for a given month (synchronous, legacy)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = CheckService(db)
    result = await service.run_checks(payload.year, payload.month)
    return result


@router.post("/run_async", status_code=202)
async def run_checks_async(
    payload: RunCheckRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start an async check run. Returns task_id for polling."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    tm = get_task_manager()
    task_id = await tm.create(f"check_{payload.year}_{payload.month}")
    await tm.update(task_id, status="pending", progress="Task created")

    asyncio.ensure_future(_run_check_task(task_id, payload.year, payload.month))

    return {"task_id": task_id, "status": "accepted"}


async def _run_check_task(task_id: str, year: int, month: int) -> None:
    """Background task that runs checks (no ARSHIN token needed)."""
    from app.core.database import AsyncSessionLocal

    tm = get_task_manager()

    async with AsyncSessionLocal() as db:
        service = CheckService(db)
        try:
            await tm.update(
                task_id,
                status="running",
                progress=f"Running checks for {year}-{month:02d}...",
            )
            result = await service.run_checks(year, month)
            await tm.update(
                task_id,
                status="completed",
                result=result,
                progress="Checks completed",
            )
        except Exception as e:
            await tm.update(
                task_id,
                status="failed",
                error=str(e),
                progress=f"Error: {e}",
            )


@router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    x_api_key: str = Header(...),
) -> dict:
    """Get status of an async task."""
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


@router.get("/token-status")
async def token_status(
    x_api_key: str = Header(...),
) -> dict:
    """Check ARSHIN Bearer token availability without blocking."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    import os
    import time
    import json
    from app.integrations.arshin_client import ArshinClient
    from app.core.config import settings

    token_file = settings.TOKEN_FILE_PATH
    used_file = token_file + ".used" if token_file else None

    data = None
    for f in [token_file, used_file]:
        if f and os.path.exists(f):
            try:
                with open(f, "r") as fh:
                    data = json.load(fh)
                break
            except Exception:
                pass

    client = ArshinClient()
    token = client.bearer_token

    if data and data.get("updated_at"):
        age_seconds = int(time.time() - data["updated_at"])
        age_minutes = age_seconds // 60
        if token:
            return {"status": "ok", "age_seconds": age_seconds, "age_minutes": age_minutes}
        return {"status": "expired", "age_seconds": age_seconds, "age_minutes": age_minutes}

    if token:
        return {"status": "ok", "age_seconds": 0, "age_minutes": 0}
    return {"status": "expired", "age_seconds": None, "age_minutes": None}


@router.get("/results/{run_id}")
async def get_results(
    run_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get check results by run ID."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.repositories.check_result_repository import CheckResultRepository
    from app.repositories.check_run_repository import CheckRunRepository

    run_repo = CheckRunRepository(db)
    result_repo = CheckResultRepository(db)

    run = await run_repo.get_by_id(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Check run not found")

    results = await result_repo.get_by_run_id(run_id)
    errors = await result_repo.get_errors(run_id)

    return {
        "run_id": run_id,
        "status": run.status,
        "year": run.year,
        "month": run.month,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "total_calibrations": run.total_calibrations,
        "total_protocols": run.total_protocols,
        "errors_count": run.errors_count,
        "warnings_count": run.warnings_count,
        "total_results": len(results),
        "errors": [
            {
                "check_type": r.check_type,
                "status": r.status,
                "comment": r.comment,
                "calibration_id": r.calibration_id,
                "protocol_data_id": r.protocol_data_id,
            }
            for r in errors
        ],
    }


@router.get("/summary")
async def get_summary(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get summary of all check runs."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.repositories.check_run_repository import CheckRunRepository

    run_repo = CheckRunRepository(db)
    latest = await run_repo.get_latest()

    return {
        "latest_run": {
            "id": latest.id,
            "year": latest.year,
            "month": latest.month,
            "status": latest.status,
            "started_at": latest.started_at.isoformat() if latest.started_at else None,
        }
        if latest
        else None,
    }
