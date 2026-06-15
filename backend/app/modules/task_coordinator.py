"""
Task Coordinator — global lock preventing concurrent heavy I/O tasks.

On Pi Zero 2 W (512MB RAM, shared SDIO bus), running the geo-indexer,
video archiver, and cloud sync simultaneously saturates the SD card
I/O and can trigger the hardware watchdog.

This module provides a global lock with fairness model:
  - Only one heavy task runs at a time
  - Cyclic tasks (indexer, archiver) yield to priority tasks (cloud sync)
  - Stale lock detection (5-minute timeout)
  - Rolling 60-second stats summary

Adapted from TeslaUSB's task_coordinator.py.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("task_coordinator")

# Lock timeout: if a task holds the lock longer than this, it's considered stale
LOCK_TIMEOUT_SECONDS = 300  # 5 minutes


class TaskCoordinator:
    """Global lock manager for heavy I/O operations.

    Usage:
        coord = TaskCoordinator()

        with coord.acquire("indexer"):
            # Run heavy indexing work
            ...

        # Check if anything is running
        if coord.is_idle():
            run_wal_checkpoint()
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._current_task: str | None = None
        self._acquired_at: float = 0.0
        self._waiter_count = 0
        # Rolling stats
        self._task_history: list[tuple[str, float, float]] = []  # (task_name, start, duration)

    def acquire(self, task_name: str, timeout: float = 3600.0) -> Optional["_TaskGuard"]:
        """Try to acquire the global lock for a named task.

        Returns a context manager guard, or None if timeout.
        Cyclic tasks (indexer, archiver) yield if there's a waiter.
        """
        deadline = time.time() + timeout

        # Fairness: cyclic tasks yield to waiters
        is_cyclic = task_name in ("indexer", "archiver", "wal_checkpoint")
        if is_cyclic and self._waiter_count > 0:
            logger.debug("Task '%s' yielding to %d waiters", task_name, self._waiter_count)
            return None

        self._waiter_count += 1
        try:
            while time.time() < deadline:
                if self._lock.acquire(blocking=False):
                    # Check for stale lock
                    if self._current_task and self._acquired_at:
                        held = time.time() - self._acquired_at
                        if held > LOCK_TIMEOUT_SECONDS:
                            logger.warning(
                                "Stale lock from '%s' (held %.0fs) — force releasing",
                                self._current_task, held,
                            )
                            self._lock.release()
                            self._lock.acquire(blocking=False)

                    self._current_task = task_name
                    self._acquired_at = time.time()
                    return _TaskGuard(self, task_name)

                time.sleep(0.5)
        finally:
            self._waiter_count -= 1

        return None

    def _release(self, task_name: str) -> None:
        """Release the global lock. Called by _TaskGuard."""
        if self._current_task == task_name:
            duration = time.time() - self._acquired_at
            self._task_history.append((task_name, self._acquired_at, duration))
            # Keep last 100 entries
            if len(self._task_history) > 100:
                self._task_history = self._task_history[-100:]

            self._current_task = None
            self._acquired_at = 0.0
        self._lock.release()

    @property
    def busy(self) -> bool:
        """Is a heavy task currently running?"""
        if not self._current_task:
            return False
        # Check for staleness
        if time.time() - self._acquired_at > LOCK_TIMEOUT_SECONDS:
            return False
        return True

    @property
    def current_task(self) -> str | None:
        if self.busy:
            return self._current_task
        return None

    @property
    def waiters(self) -> int:
        return self._waiter_count

    def is_idle(self) -> bool:
        return not self.busy

    def get_status(self) -> dict:
        """Return coordinator status for system health API."""
        return {
            "busy": self.busy,
            "current_task": self.current_task,
            "elapsed_seconds": round(time.time() - self._acquired_at, 1) if self._acquired_at else 0,
            "waiters": self._waiter_count,
            "recent_tasks": len(self._task_history),
            "last_5": [
                {"task": t, "duration_s": round(d, 1)}
                for t, _, d in self._task_history[-5:]
            ],
        }


class _TaskGuard:
    """Context manager returned by TaskCoordinator.acquire()."""

    def __init__(self, coordinator: TaskCoordinator, task_name: str):
        self._coord = coordinator
        self._task = task_name

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._coord._release(self._task)


# Application-wide singleton
coordinator = TaskCoordinator()
