"""Scheduler service with manual/auto modes."""

import asyncio
import json
import os
from datetime import datetime
from typing import Optional

from app.services.job_queue_service import JobQueueService

# State file for scheduler configuration
STATE_FILE = os.environ.get("SCHEDULER_STATE", "/tmp/scheduler_state.json")


class SchedulerService:
    """Advanced scheduler: manual mode, auto mode, on-demand checks.
    
    Modes:
      - manual: no automatic scheduling, only manual triggers
      - auto: schedule on 1st day of month at 09:00
    """

    def __init__(self, queue_service: JobQueueService) -> None:
        self.queue = queue_service
        self._stop_event = asyncio.Event()
        self._state = self._load_state()

    def _load_state(self) -> dict:
        """Load scheduler state from file."""
        default = {
            "mode": "manual",  # manual | auto
            "last_run": None,
            "next_scheduled": None,
            "auto_time": "09:00",  # HH:MM
            "auto_day": 1,  # day of month when check runs
            "month_offset": -1,  # which month to check: -1=previous, -2=two months ago, etc.
        }
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE) as f:
                    loaded = json.load(f)
                    default.update(loaded)
        except Exception:
            pass
        return default

    def _save_state(self) -> None:
        """Save scheduler state to file."""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self._state, f, indent=2)
        except Exception:
            pass

    def set_mode(self, mode: str) -> None:
        """Switch mode: manual or auto."""
        if mode not in ("manual", "auto"):
            raise ValueError("Mode must be 'manual' or 'auto'")
        self._state["mode"] = mode
        self._save_state()
        print(f"[Scheduler] Mode set to: {mode}")

    def get_mode(self) -> str:
        """Get current mode."""
        return self._state["mode"]

    def is_auto(self) -> bool:
        """Check if auto mode is enabled."""
        return self._state["mode"] == "auto"

    async def start(self) -> None:
        """Start scheduler loop."""
        self._stop_event.clear()
        print(f"[Scheduler] Started in {self._state['mode']} mode")
        
        while not self._stop_event.is_set():
            try:
                if self.is_auto():
                    await self._check_and_schedule_auto()
            except Exception as e:
                print(f"[Scheduler] Error: {e}")
            
            await asyncio.sleep(60)  # Check every minute

    async def _check_and_schedule_auto(self) -> None:
        """Check if it's time for automatic monthly check."""
        now = datetime.utcnow()
        
        # Parse auto time (default 09:00)
        hour, minute = map(int, self._state["auto_time"].split(":"))
        
        # Only on configured day, at configured time
        if now.day == self._state["auto_day"] and now.hour == hour and now.minute < 5:
            # Calculate target month based on offset
            # Example: offset=-2, current=July(7) → target=May(5)
            offset = self._state.get("month_offset", -1)
            target_month = now.month + offset
            target_year = now.year
            
            # Handle year rollover
            while target_month <= 0:
                target_month += 12
                target_year -= 1
            while target_month > 12:
                target_month -= 12
                target_year += 1
            
            year = target_year
            month = target_month
            
            # Check if not already queued
            from app.repositories.job_repository import JobRepository
            repo = JobRepository(self.queue.db)
            
            existing = await repo.list_all(limit=20)
            already_queued = any(
                j.year == year and j.month == month and j.status in ["pending", "running", "paused"]
                for j in existing
            )
            
            if not already_queued:
                print(f"[Scheduler] Auto-scheduling check for {month:02d}.{year}")
                await self.queue.enqueue_auto(year, month, triggered_by="cron")
                self._state["last_run"] = now.isoformat()
                self._save_state()
            
            # Sleep for 1 hour to avoid duplicates
            await asyncio.sleep(3600)

    async def run_manual(self, year: int, month: int, triggered_by: str = "user") -> dict:
        """Manually trigger a check for specific month.
        
        Works in both manual and auto modes.
        """
        print(f"[Scheduler] Manual check requested: {month:02d}.{year}")
        job = await self.queue.enqueue_manual(year, month, triggered_by=triggered_by)
        return {
            "job_id": job.id,
            "year": year,
            "month": month,
            "status": "queued",
            "mode": self._state["mode"],
        }

    def stop(self) -> None:
        """Stop scheduler."""
        self._stop_event.set()
        print("[Scheduler] Stopped")

    def get_status(self) -> dict:
        """Get scheduler status for UI."""
        now = datetime.utcnow()
        
        # Calculate next scheduled
        next_scheduled = None
        if self.is_auto():
            if now.day < self._state["auto_day"] or (now.day == self._state["auto_day"] and now.hour < int(self._state["auto_time"].split(":")[0])):
                next_date = now.replace(day=self._state["auto_day"])
            else:
                # Next month
                if now.month == 12:
                    next_date = now.replace(year=now.year + 1, month=1, day=self._state["auto_day"])
                else:
                    next_date = now.replace(month=now.month + 1, day=self._state["auto_day"])
            
            hour, minute = self._state["auto_time"].split(":")
            next_scheduled = next_date.replace(hour=int(hour), minute=int(minute), second=0).isoformat()
        
        return {
            "mode": self._state["mode"],
            "is_auto": self.is_auto(),
            "last_run": self._state.get("last_run"),
            "next_scheduled": next_scheduled,
            "auto_time": self._state["auto_time"],
            "auto_day": self._state["auto_day"],
            "month_offset": self._state.get("month_offset", -1),
            "settings": {
                "description": {
                    "auto_day": f"Day {self._state['auto_day']} of each month",
                    "auto_time": f"At {self._state['auto_time']}",
                    "month_offset": f"Check month: current {self._state.get('month_offset', -1)} = {self._get_example_month()}",
                }
            }
        }
    
    def _get_example_month(self) -> str:
        """Show example of which month will be checked."""
        now = datetime.utcnow()
        offset = self._state.get("month_offset", -1)
        target = now.month + offset
        year = now.year
        while target <= 0:
            target += 12
            year -= 1
        while target > 12:
            target -= 12
            year += 1
        return f"{target:02d}.{year}"
    
    def update_settings(self, **kwargs) -> dict:
        """Update scheduler settings."""
        allowed = {"mode", "auto_time", "auto_day", "month_offset"}
        updated = {}
        
        for key, value in kwargs.items():
            if key in allowed:
                # Validation
                if key == "mode" and value not in ("manual", "auto"):
                    raise ValueError("Mode must be 'manual' or 'auto'")
                if key == "auto_day" and not (1 <= int(value) <= 31):
                    raise ValueError("Day must be 1-31")
                if key == "month_offset" and not (-12 <= int(value) <= 0):
                    raise ValueError("Month offset must be -12 to 0")
                
                self._state[key] = value
                updated[key] = value
        
        self._save_state()
        return updated
