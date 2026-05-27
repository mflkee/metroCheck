"""Cron service for automatic monthly checks."""

import asyncio
from datetime import datetime, timedelta

from app.core.config import settings
from app.services.job_queue_service import JobQueueService


class CronService:
    """Schedules automatic checks at the start of each month."""

    def __init__(self, queue_service: JobQueueService) -> None:
        self.queue = queue_service
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start cron scheduler."""
        self._stop_event.clear()
        while not self._stop_event.is_set():
            now = datetime.utcnow()
            
            # Schedule check for previous month on 1st day of current month at 09:00
            if now.day == 1 and now.hour == 9 and now.minute < 5:
                # Previous month
                if now.month == 1:
                    year = now.year - 1
                    month = 12
                else:
                    year = now.year
                    month = now.month - 1
                
                # Check if not already queued
                # (in real implementation, check DB)
                await self.queue.enqueue_auto(year, month, triggered_by="cron")
                
                # Sleep 1 hour to avoid duplicates
                await asyncio.sleep(3600)
            else:
                # Sleep until next check
                await asyncio.sleep(60)

    def stop(self) -> None:
        """Stop cron scheduler."""
        self._stop_event.set()
