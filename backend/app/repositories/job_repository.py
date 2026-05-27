"""Job repository."""

from typing import Optional

from sqlalchemy import select, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job


class JobRepository:
    """Repository for job queue operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(
        self,
        year: int,
        month: int,
        job_type: str = "auto",
        priority: int = 0,
        triggered_by: str = "system",
    ) -> Job:
        job = Job(
            year=year,
            month=month,
            job_type=job_type,
            priority=priority,
            triggered_by=triggered_by,
            status="pending",
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def get_by_id(self, job_id: int) -> Optional[Job]:
        result = await self.db.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def get_next_pending(self) -> Optional[Job]:
        """Get highest priority pending job."""
        result = await self.db.execute(
            select(Job)
            .where(Job.status.in_(["pending", "paused"]))
            .order_by(desc(Job.priority), asc(Job.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_running(self) -> Optional[Job]:
        """Get currently running job."""
        result = await self.db.execute(
            select(Job).where(Job.status == "running").limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self,
        job_id: int,
        status: str,
        progress: str = "",
        progress_percent: int = 0,
        error_message: Optional[str] = None,
        check_run_id: Optional[int] = None,
        result_json: Optional[str] = None,
        total_devices: Optional[int] = None,
        processed_devices: Optional[int] = None,
        current_device: Optional[str] = None,
    ) -> None:
        job = await self.get_by_id(job_id)
        if job:
            job.status = status
            job.progress = progress
            job.progress_percent = progress_percent
            if error_message:
                job.error_message = error_message
            if check_run_id:
                job.check_run_id = check_run_id
            if result_json:
                job.result_json = result_json
            if total_devices is not None:
                job.total_devices = total_devices
            if processed_devices is not None:
                job.processed_devices = processed_devices
            if current_device:
                job.current_device = current_device
            await self.db.commit()

    async def list_all(self, limit: int = 50) -> list[Job]:
        result = await self.db.execute(
            select(Job).order_by(desc(Job.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status(self, status: str, limit: int = 50) -> list[Job]:
        result = await self.db.execute(
            select(Job)
            .where(Job.status == status)
            .order_by(desc(Job.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def cancel_job(self, job_id: int) -> bool:
        job = await self.get_by_id(job_id)
        if job and job.status in ["pending", "paused", "running"]:
            job.status = "cancelled"
            await self.db.commit()
            return True
        return False

    async def pause_job(self, job_id: int) -> bool:
        job = await self.get_by_id(job_id)
        if job and job.status == "pending":
            job.status = "paused"
            await self.db.commit()
            return True
        return False

    async def resume_job(self, job_id: int) -> bool:
        job = await self.get_by_id(job_id)
        if job and job.status == "paused":
            job.status = "pending"
            await self.db.commit()
            return True
        return False
