"""
File watcher — detects new Tesla dashcam videos and emits FILE_DETECTED events.

Adapted from TeslaUSB's file_watcher_service.py.
Uses watchfiles (Python, cross-platform) instead of Linux inotify.
Falls back to polling when watchfiles is unavailable.
"""

import asyncio
import logging
from pathlib import Path

from app.config import config
from app.event_bus import Event, EventType, event_bus

logger = logging.getLogger("ingestion.watcher")


class FileWatcher:
    """Watches a directory for new MP4 files and emits events."""

    def __init__(self, watch_dir: str | None = None):
        self.watch_dir = Path(watch_dir or config.ingestion.watch_dir)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._running = True
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("File watcher started: %s", self.watch_dir)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self) -> None:
        """Main watch loop — tries watchfiles, falls back to polling."""
        try:
            from watchfiles import awatch
            async for changes in awatch(str(self.watch_dir)):
                if not self._running:
                    break
                for _, path in changes:
                    if path.endswith(".mp4"):
                        await self._on_new_file(Path(path))
        except ImportError:
            logger.info("watchfiles not available, using polling fallback")
            while self._running:
                await self._poll()
                await asyncio.sleep(30)

    async def _poll(self) -> None:
        """Poll the watch directory for new MP4 files."""
        if not self.watch_dir.exists():
            return
        for mp4 in self.watch_dir.glob("**/*.mp4"):
            await self._on_new_file(mp4)

    async def scan_all(self) -> list[str]:
        """Manually scan the watch directory for ALL existing MP4 files.

        Use this for initial import of existing dashcam footage.
        Returns list of file paths that were enqueued.
        """
        if not self.watch_dir.exists():
            logger.warning("Watch directory does not exist: %s", self.watch_dir)
            return []

        found = []
        for mp4 in sorted(self.watch_dir.glob("**/*.mp4")):
            await self._on_new_file(mp4)
            found.append(str(mp4.absolute()))
            # Small delay between emits to avoid overwhelming the event bus
            await asyncio.sleep(0.1)

        logger.info("Scan complete: %d files enqueued", len(found))
        return found

    async def _on_new_file(self, path: Path) -> None:
        logger.info("New file detected: %s", path)
        await event_bus.emit(Event(
            type=EventType.FILE_DETECTED,
            data={"path": str(path.absolute()), "size": path.stat().st_size},
        ))
