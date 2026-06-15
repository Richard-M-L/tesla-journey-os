"""
Archive module — copies processed video files to durable storage.

Adapted from TeslaUSB's archive_producer.py and archive_worker.py.
Simplified for TJOS: no USB gadget mode, just file copy to archive directory.
"""

import logging
import shutil
from pathlib import Path

from app.config import config
from app.event_bus import Event, EventType, event_bus

logger = logging.getLogger("archive")


async def register() -> None:
    """Register archive listeners on the event bus."""
    event_bus.subscribe(EventType.FILE_INDEXED, on_file_indexed)


async def on_file_indexed(event: Event) -> None:
    """After a file is indexed, copy it to the archive directory."""
    src = Path(event.data["file_path"])
    archive_dir = Path(config.ingestion.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    dest = archive_dir / src.name

    # Don't re-archive files that are already in the archive dir
    if str(archive_dir) in str(src.absolute()):
        return

    try:
        if not dest.exists():
            shutil.copy2(src, dest)
            logger.info("Archived: %s → %s", src.name, dest)

        await event_bus.emit(Event(
            type=EventType.ARCHIVE_COMPLETED,
            data={"source_path": str(src), "dest_path": str(dest)},
        ))
    except OSError as e:
        logger.error("Archive failed: %s → %s: %s", src, dest, e)
        await event_bus.emit(Event(
            type=EventType.ARCHIVE_FAILED,
            data={"source_path": str(src), "dest_path": str(dest), "error": str(e)},
        ))
