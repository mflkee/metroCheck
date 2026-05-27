"""Job queue service — manages check execution queue with priorities."""

import asyncio
import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.arshin_client import ArshinClient
from app.models.job import Job
from app.repositories.job_repository import JobRepository
from app.services.check_service import CheckService
from app.services.task_manager import get_task_manager


class JobQueueService:
    """Manages prioritized job queue for check runs.
    
    Priority levels:
      - manual (priority=10): user-triggered, runs immediately
      - auto (priority=0): cron-triggered, runs when idle
    
    Only ONE job runs at a time. Manual jobs pause auto jobs.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = JobRepository(db)
        self._current_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def enqueue_manual(
        self,
        year: int,
        month: int,
        triggered_by: str = "user",
    ) -> Job:
        """Add manual job with high priority."""
        # Cancel any pending auto jobs
        pending_auto = await self.repo.list_by_status("pending")
        for job in pending_auto:
            if job.job_type == "auto":
                await self.repo.cancel_job(job.id)
        
        return await self.repo.create(
            year=year,
            month=month,
            job_type="manual",
            priority=10,
            triggered_by=triggered_by,
        )

    async def enqueue_auto(
        self,
        year: int,
        month: int,
        triggered_by: str = "cron",
    ) -> Job:
        """Add automatic job with low priority."""
        return await self.repo.create(
            year=year,
            month=month,
            job_type="auto",
            priority=0,
            triggered_by=triggered_by,
        )

    async def start_worker(self) -> None:
        """Start background worker that processes jobs."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            try:
                await self._process_next_job()
            except Exception as e:
                print(f"[JobQueue] Worker error: {e}")
            await asyncio.sleep(5)  # Poll every 5 seconds

    def stop_worker(self) -> None:
        """Signal worker to stop."""
        self._stop_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def _process_next_job(self) -> None:
        """Pick and run the next highest priority job."""
        # Check if something is already running
        running = await self.repo.get_running()
        if running:
            return  # Wait for current job to finish

        # Get next pending job
        job = await self.repo.get_next_pending()
        if not job:
            return

        # Mark as running
        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        # Run the job
        try:
            result = await self._execute_job(job)
            job.status = "completed"
            job.result_json = json.dumps(result)
            job.progress = "Completed"
            job.progress_percent = 100
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.progress = "Cancelled"
            raise
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.progress = f"Failed: {e}"
        finally:
            job.completed_at = datetime.utcnow()
            await self.db.commit()

    async def _execute_job(self, job: Job) -> dict[str, Any]:
        """Execute a single check job."""
        tm = get_task_manager()
        task_id = await tm.create(f"job_{job.id}_{job.year}_{job.month}")
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Ensuring ARSHIN token...",
            progress_percent=5,
        )

        # Step 1: Ensure token (may wait for Зонов)
        client = ArshinClient()
        token = client.bearer_token
        if not token:
            await self.repo.update_status(
                job.id,
                status="running",
                progress="Waiting for Зонов to login via Госуслуги...",
                progress_percent=5,
            )
            await tm.update(task_id, status="waiting_token", progress="Waiting for ARSHIN token...")
            token = await client._request_new_token()

        await self.repo.update_status(
            job.id,
            status="running",
            progress="Fetching calibrations from ARSHIN...",
            progress_percent=15,
        )

        # Step 2: Fetch calibrations (public API, no token needed)
        from app.services.arshin_service import ArshinService
        arshin_service = ArshinService(self.db)
        
        cal_result = await arshin_service.fetch_and_save_calibrations(job.year, job.month)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Fetched {cal_result['saved']} calibrations",
            progress_percent=35,
        )

        # Step 3: Fetch LK details (needs token)
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Fetching LK details...",
            progress_percent=50,
        )
        
        lk_result = await arshin_service.fetch_lk_details(job.year, job.month)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Updated {lk_result['updated']} LK details",
            progress_percent=60,
        )

        # Step 4: Fetch LK data2
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Fetching extended data...",
            progress_percent=70,
        )
        
        data2_result = await arshin_service.fetch_lk_data2(job.year, job.month)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Updated {data2_result['updated']} extended records",
            progress_percent=80,
        )

        # Step 5: Run checks
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Running protocol checks...",
            progress_percent=85,
        )
        
        check_service = CheckService(self.db)
        check_result = await check_service.run_checks(job.year, job.month)
        
        # Update job with check_run_id
        if check_result.get("run_id"):
            job.check_run_id = check_result["run_id"]

        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Checks: {check_result.get('errors', 0)} errors, {check_result.get('warnings', 0)} warnings",
            progress_percent=95,
        )

        return {
            "calibrations": cal_result,
            "lk_details": lk_result,
            "lk_data2": data2_result,
            "checks": check_result,
        }

    async def cancel_job(self, job_id: int) -> bool:
        """Cancel a pending or running job."""
        job = await self.repo.get_by_id(job_id)
        if not job:
            return False
        
        if job.status == "running" and self._current_task:
            self._current_task.cancel()
        
        return await self.repo.cancel_job(job_id)

    async def pause_job(self, job_id: int) -> bool:
        """Pause a pending job."""
        return await self.repo.pause_job(job_id)

    async def resume_job(self, job_id: int) -> bool:
        """Resume a paused job."""
        return await self.repo.resume_job(job_id)

    async def get_queue_status(self) -> dict[str, Any]:
        """Get current queue status."""
        running = await self.repo.get_running()
        pending = await self.repo.list_by_status("pending")
        paused = await self.repo.list_by_status("paused")
        recent = await self.repo.list_all(limit=10)
        
        return {
            "running": self._job_to_dict(running) if running else None,
            "pending": [self._job_to_dict(j) for j in pending],
            "paused": [self._job_to_dict(j) for j in paused],
            "recent": [self._job_to_dict(j) for j in recent],
        }

    @staticmethod
    def _job_to_dict(job: Job) -> dict[str, Any]:
        return {
            "id": job.id,
            "year": job.year,
            "month": job.month,
            "job_type": job.job_type,
            "status": job.status,
            "priority": job.priority,
            "progress": job.progress,
            "progress_percent": job.progress_percent,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "triggered_by": job.triggered_by,
            "check_run_id": job.check_run_id,
            "error_message": job.error_message,
        }


# Singleton instance for background worker
_queue_service: Optional[JobQueueService] = None


def get_queue_service(db: AsyncSession) -> JobQueueService:
    return JobQueueService(db)
