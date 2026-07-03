"""Job queue API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.v1.dependencies.auth import get_current_user
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add manual check job (high priority, cancels pending auto jobs)."""
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add automatic check job (low priority)."""
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
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a pending or running job."""
    service = get_queue_service(db)
    success = await service.cancel_job(job_id, db=db)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be cancelled")

    return {"status": "cancelled", "job_id": job_id}


@router.post("/pause/{job_id}")
async def pause_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pause a pending job."""
    service = get_queue_service(db)
    success = await service.pause_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be paused")

    return {"status": "paused", "job_id": job_id}


@router.post("/resume/{job_id}")
async def resume_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resume a paused job."""
    service = get_queue_service(db)
    success = await service.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or cannot be resumed")

    return {"status": "resumed", "job_id": job_id}


@router.get("/status")
async def queue_status(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current queue status (running, pending, paused, recent)."""
    service = get_queue_service(db)
    return await service.get_queue_status()


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get job details."""
    from app.repositories.job_repository import JobRepository
    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobQueueService._job_to_dict(job)


@router.get("/{job_id}/download-report")
async def download_job_report(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download latest existing report for a job (works even if interrupted/failed)."""
    from app.repositories.job_repository import JobRepository
    from fastapi.responses import FileResponse
    import os
    import glob

    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Search for existing reports in /tmp/reports and /reports
    reports_dirs = ["/tmp/reports", "/reports"]
    search_patterns = [
        f"*{job.year}_{job.month:02d}*.xlsx",
        f"*interim*{job.year}_{job.month:02d}*.xlsx",
    ]

    candidates = []
    for directory in reports_dirs:
        if not os.path.isdir(directory):
            continue
        for pattern in search_patterns:
            for path in glob.glob(os.path.join(directory, pattern)):
                try:
                    mtime = os.path.getmtime(path)
                    candidates.append((mtime, path))
                except OSError:
                    pass

    if not candidates:
        raise HTTPException(status_code=404, detail="No report files found for this job")

    # Pick the newest file
    candidates.sort(reverse=True)
    file_path = candidates[0][1]
    filename = os.path.basename(file_path)

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/{job_id}/generate-report")
async def generate_job_report(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Generate and download current report for a job (interim or final)."""
    from app.repositories.job_repository import JobRepository
    from app.services.report_service import ReportService
    from fastapi.responses import FileResponse
    import os

    repo = JobRepository(db)
    job = await repo.get_by_id(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Generate report based on current data
    report_service = ReportService(db)
    
    # Always generate fresh interim report (avoids stale cached files)
    result = await report_service.generate_interim_report(job.year, job.month, job_id=job.id)

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    file_path = result.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found")

    filename = result.get("filename", f"report_{job.year}_{job.month:02d}.xlsx")
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a job by ID."""
    from app.repositories.job_repository import JobRepository
    repo = JobRepository(db)
    deleted = await repo.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}

