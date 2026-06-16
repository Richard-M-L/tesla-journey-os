"""
Task coordinator — tracks background task status for health reporting.
"""

import logging
import time

logger = logging.getLogger("task_coordinator")


class TaskCoordinator:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._started_at = time.time()

    def register(self, name: str, status: str = "running") -> None:
        self._tasks[name] = {
            "status": status,
            "started_at": time.time(),
        }

    def update(self, name: str, status: str) -> None:
        if name in self._tasks:
            self._tasks[name]["status"] = status
            self._tasks[name]["updated_at"] = time.time()

    def get_status(self) -> dict:
        return {
            "task_count": len(self._tasks),
            "uptime_seconds": int(time.time() - self._started_at),
            "tasks": {
                name: data["status"]
                for name, data in self._tasks.items()
            },
        }


coordinator = TaskCoordinator()
