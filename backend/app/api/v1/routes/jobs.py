"""Job queue API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.services.job_queue_service import JobQueueService, get_queue_service

router = APIRouter()


class EnqueueRequest(BaseModel):
    year: int
    month: int


class JobResponse(BaseModel):
    id: int
    year: int
    month: int
    job_type: str
    status: str
    priority: int
    progress: str
    progress_percent: int
    triggered_by: str
    created_at: str | None


@router.post("/enqueue", status_code=202)
async def enqueue_manual(
    payload: EnqueueRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add manual check job (high priority, cancels pending auto jobs)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    job = await service.enqueue_manual(
        year=payload.year,
        month=payload.month,
        triggered_by="user",
    )

    return {
        "job_id": job.id,
        "status": "accepted",
        "message": f"Manual check queued for {payload.year}-{payload.month:02d}",
    }


@router.post("/enqueue-auto", status_code=202)
async def enqueue_auto(
    payload: EnqueueRequest,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add automatic check job (low priority)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    job = await service.enqueue_auto(
        year=payload.year,
        month=payload.month,
        triggered_by="cron",
    )

    return {
        "job_id": job.id,
        "status": "accepted",
        "message": f"Auto check queued for {payload.year}-{payload.month:02d}",
    }


@router.post("/cancel/{job_id}")
async def cancel_job(
    job_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a pending or running job."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    success = await service.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be cancelled")

    return {"status": "cancelled", "job_id": job_id}


@router.post("/pause/{job_id}")
async def pause_job(
    job_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pause a pending job."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    success = await service.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be paused")

    return {"status": "paused", "job_id": job_id}


@router.post("/resume/{job_id}")
async def resume_job(
    job_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resume a paused job."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    success = await service.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be resumed")

    return {"status": "resumed", "job_id": job_id}


@router.get("/status")
async def queue_status(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current queue status (running, pending, paused, recent)."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    service = get_queue_service(db)
    return await service.get_queue_status()


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get job details."""
    if x_api_key != settings.FASTAPI_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    from app.repositories.job_repository import JobRepository
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobQueueService._job_to_dict(job)
