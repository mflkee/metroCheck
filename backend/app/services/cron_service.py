"""Cron service for automatic monthly checks."""

import asyncio
from datetime import datetime

from app.services.job_queue_service import JobQueueService


class CronService:
    """Schedules automatic checks at the start of each month.
    
    Logic:
      - 1st day of month at 09:00: enqueue check for PREVIOUS month
      - Queue system waits for token automatically
      - Non-stop mode: after completion, waits for next month
    """

    def __init__(self, queue_service: JobQueueService) -> None:
        self.queue = queue_service
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start cron scheduler."""
        self._stop_event.clear()
        print("[Cron] Scheduler started")
        
        while not self._stop_event.is_set():
            try:
                await self._check_and_schedule()
            except Exception as e:
                print(f"[Cron] Error: {e}")
            
            # Check every minute
            await asyncio.sleep(60)

    async def _check_and_schedule(self) -> None:
        """Check if it's time to run monthly check."""
        now = datetime.utcnow()
        
        # Only on 1st day of month, between 09:00 and 09:05
        if now.day == 1 and now.hour == 9 and now.minute < 5:
            # Calculate previous month
            if now.month == 1:
                year = now.year - 1
                month = 12
            else:
                year = now.year
                month = now.month - 1
            
            # Check if not already queued or running
            from app.repositories.job_repository import JobRepository
            repo = JobRepository(self.queue.db)
            
            existing = await repo.list_all(limit=20)
            already_queued = any(
                j.year == year and j.month == month and j.status in ["pending", "running", "paused"]
                for j in existing
            )
            
            if not already_queued:
                print(f"[Cron] Scheduling auto check for {month:02d}.{year}")
                await self.queue.enqueue_auto(year, month, triggered_by="cron")
            else:
                print(f"[Cron] Check for {month:02d}.{year} already queued/running")
            
            # Sleep for 1 hour to avoid duplicate scheduling
            await asyncio.sleep(3600)

    def stop(self) -> None:
        """Stop cron scheduler."""
        self._stop_event.set()
        print("[Cron] Scheduler stopped")
