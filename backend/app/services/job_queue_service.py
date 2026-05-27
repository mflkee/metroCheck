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
from app.services.email_service import EmailService
from app.services.task_manager import get_task_manager


class JobQueueService:
    """Manages prioritized job queue for check runs.
    
    Workflow:
      1. Auto mode: waits for token, then checks previous month non-stop
      2. Manual mode: interrupts auto, runs immediately
      3. After completion: sends email report
      4. If token expires mid-check: waits and resumes
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = JobRepository(db)
        self.email = EmailService()
        self._current_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    async def enqueue_manual(
        self,
        year: int,
        month: int,
        triggered_by: str = "user",
    ) -> Job:
        """Add manual job with high priority. Cancels auto jobs."""
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
            await asyncio.sleep(5)

    def stop_worker(self) -> None:
        """Signal worker to stop."""
        self._stop_event.set()
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

    async def _process_next_job(self) -> None:
        """Pick and run the next highest priority job."""
        running = await self.repo.get_running()
        if running:
            return

        job = await self.repo.get_next_pending()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        await self.db.commit()

        try:
            result = await self._execute_job(job)
            job.status = "completed"
            job.result_json = json.dumps(result)
            job.progress = "Completed"
            job.progress_percent = 100
            job.processed_devices = job.total_devices
            
            # Send email report
            await self._send_report(job, result)
            
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
        """Execute a single check job with per-device tracking."""
        tm = get_task_manager()
        task_id = await tm.create(f"job_{job.id}_{job.year}_{job.month}")
        
        # Step 1: Ensure token (wait if needed)
        client = ArshinClient()
        token = client.bearer_token
        if not token:
            await self.repo.update_status(
                job.id,
                status="running",
                progress="Ожидание токена АРШИН... Зонов должен залогиниться через Госуслуги",
                progress_percent=0,
            )
            await tm.update(task_id, status="waiting_token", progress="Waiting for ARSHIN token...")
            job.waiting_for_token = True
            await self.db.commit()
            
            token = await client._request_new_token()
            job.waiting_for_token = False
            await self.db.commit()

        await self.repo.update_status(
            job.id,
            status="running",
            progress="Загрузка поверок из АРШИН...",
            progress_percent=5,
        )

        # Step 2: Fetch calibrations
        from app.services.arshin_service import ArshinService
        arshin_service = ArshinService(self.db)
        
        cal_result = await arshin_service.fetch_and_save_calibrations(job.year, job.month)
        total_devices = cal_result.get('saved', 0)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Загружено {cal_result['saved']} поверок",
            progress_percent=15,
            total_devices=total_devices,
        )

        # Step 3: Fetch LK details (with token check)
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Загрузка данных из ЛК АРШИН...",
            progress_percent=25,
            processed_devices=0,
        )
        
        # Check token before LK requests
        if not client.bearer_token:
            await self._wait_for_token(job, client)
        
        lk_result = await arshin_service.fetch_lk_details(job.year, job.month)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Обновлено {lk_result['updated']} записей из ЛК",
            progress_percent=45,
            processed_devices=total_devices // 3,
        )

        # Step 4: Fetch LK data2
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Загрузка расширенных данных...",
            progress_percent=55,
        )
        
        if not client.bearer_token:
            await self._wait_for_token(job, client)
        
        data2_result = await arshin_service.fetch_lk_data2(job.year, job.month)
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Обновлено {data2_result['updated']} расширенных записей",
            progress_percent=70,
            processed_devices=total_devices * 2 // 3,
        )

        # Step 5: Run checks
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Проверка протоколов...",
            progress_percent=80,
        )
        
        check_service = CheckService(self.db)
        check_result = await check_service.run_checks(job.year, job.month)
        
        if check_result.get("run_id"):
            job.check_run_id = check_result["run_id"]

        await self.repo.update_status(
            job.id,
            status="running",
            progress=f"Проверка завершена: {check_result.get('errors', 0)} ошибок, {check_result.get('warnings', 0)} предупреждений",
            progress_percent=95,
            processed_devices=total_devices,
        )

        return {
            "calibrations": cal_result,
            "lk_details": lk_result,
            "lk_data2": data2_result,
            "checks": check_result,
        }

    async def _wait_for_token(self, job: Job, client: ArshinClient) -> None:
        """Wait for token and update job status."""
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Токен истёк! Ожидание нового токена от Зонова...",
            progress_percent=job.progress_percent,
        )
        job.waiting_for_token = True
        await self.db.commit()
        
        await client._request_new_token()
        
        job.waiting_for_token = False
        await self.db.commit()
        
        await self.repo.update_status(
            job.id,
            status="running",
            progress="Токен получен, продолжение работы...",
            progress_percent=job.progress_percent,
        )

    async def _send_report(self, job: Job, result: dict[str, Any]) -> None:
        """Send email report after completion."""
        checks = result.get("checks", {})
        
        await self.email.send_check_report(
            year=job.year,
            month=job.month,
            total_devices=job.total_devices,
            errors=checks.get("errors", 0),
            warnings=checks.get("warnings", 0),
            missing=checks.get("missing", 0),
            check_run_id=job.check_run_id or 0,
            report_url=f"http://100.89.59.195:8002/api/v1/checks/results/{job.check_run_id}" if job.check_run_id else None,
        )
        
        job.email_sent = True
        await self.db.commit()

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
        """Get current queue status with device progress."""
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
            "total_devices": job.total_devices,
            "processed_devices": job.processed_devices,
            "current_device": job.current_device,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "triggered_by": job.triggered_by,
            "check_run_id": job.check_run_id,
            "error_message": job.error_message,
            "waiting_for_token": job.waiting_for_token,
            "email_sent": job.email_sent,
        }


_queue_service: Optional[JobQueueService] = None


def get_queue_service(db: AsyncSession) -> JobQueueService:
    return JobQueueService(db)
