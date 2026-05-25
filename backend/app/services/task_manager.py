"""Async task manager for long-running operations."""

import asyncio
import time
import uuid
from typing import Any


class TaskManager:
    """Simple in-memory task tracker with status updates."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, name: str) -> str:
        task_id = uuid.uuid4().hex[:12]
        async with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "name": name,
                "status": "pending",
                "created_at": time.time(),
                "updated_at": time.time(),
                "result": None,
                "error": None,
                "progress": "",
            }
        return task_id

    async def update(self, task_id: str, **kwargs: Any) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.update(kwargs)
                task["updated_at"] = time.time()

    async def get(self, task_id: str) -> dict[str, Any] | None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                return dict(task)
            return None

    async def cleanup_old(self, max_age: float = 86400) -> int:
        now = time.time()
        async with self._lock:
            old = [tid for tid, t in self._tasks.items()
                   if now - t["created_at"] > max_age]
            for tid in old:
                del self._tasks[tid]
        return len(old)


_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
