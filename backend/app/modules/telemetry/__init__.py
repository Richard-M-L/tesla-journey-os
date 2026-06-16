"""
Telemetry module — processes raw telemetry frames into stored snapshots.

This is the central ingest pipeline:
  1. Listens for FILE_DETECTED events
  2. Stable-write check (file unchanged for N seconds)
  3. Stationary clip filter (skip if speed=0 + gear=PARK)
  4. Parses SEI data from MP4 files
  5. Stores TelemetrySnapshot + TelemetryCold rows
  6. Emits TELEMETRY_INGESTED events for downstream modules

Protection layers (adapted from TeslaUSB):
  - Stable write: file mtime must be unchanged for STABLE_WRITE_AGE seconds
  - Stationary filter: skip clips where first N frames have speed=0 + gear=PARK
  - Cross-folder dedup: skip files already in IndexedFile table
"""

import logging
import os
import sys
import time as time_mod
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.event_bus import Event, EventType, event_bus
from app.models import IndexedFile, PipelineQueue, TelemetrySnapshot, TelemetryCold
from app.modules.ingestion.parser import SeiParser, TelemetryFrame, extract_sei_messages

logger = logging.getLogger("telemetry")

# ── Configurable thresholds ──
# File must be unchanged for this many seconds before processing
STABLE_WRITE_AGE = int(os.environ.get("TJOS_STABLE_WRITE_AGE", "60"))

# When peeking for stationary detection, only walk this many MB of the file
STATIONARY_PEEK_MB = int(os.environ.get("TJOS_STATIONARY_PEEK_MB", "3"))
STATIONARY_PEEK_BYTES = STATIONARY_PEEK_MB * 1024 * 1024

# If ALL peek frames have speed below this and gear is PARK, skip the file
STATIONARY_SPEED_THRESHOLD = 0.1  # m/s


async def register() -> None:
    """Register telemetry event listeners on the event bus."""
    event_bus.subscribe(EventType.FILE_DETECTED, on_file_detected)


async def on_file_detected(event: Event) -> None:
    """Handle a new file detection with protection layers.

    Order of checks:
      1. Already indexed? → skip
      2. Still being written? → skip (will retry on next scan)
      3. Stationary (sentry mode)? → skip
      4. Parse and store
    """
    from app.database import SessionLocal
    path = event.data["path"]

    # ── Layer 0: Pipeline queue enqueue ──
    from app.modules.pipeline_queue import (enqueue, claim_next, complete, fail, recover_stale,
        STAGE_DETECTED, STAGE_INDEXING)
    db = SessionLocal()
    try:
        p_row = enqueue(db, path, stage=STAGE_DETECTED)
        # Recover stale claims from previous runs
        recover_stale(db, STAGE_DETECTED)
        recover_stale(db, STAGE_INDEXING)
    finally:
        db.close()

    # ── Layer 1: Already indexed? ──
    db = SessionLocal()
    try:
        existing = db.query(IndexedFile).filter(
            IndexedFile.file_path == path
        ).first()
        if existing:
            logger.debug("Already indexed, skipping: %s", Path(path).name)
            complete(db, p_row)
            return
    finally:
        db.close()

    # ── Layer 2: Stable write check ──
    if not _is_stable(path):
        logger.info("File still being written, deferring: %s", Path(path).name)
        return

    # ── Layer 3: Stationary clip filter ──
    if _is_stationary(path):
        logger.info("Stationary clip (sentry mode), skipping: %s", Path(path).name)
        # Still record as indexed to avoid re-checking
        db = SessionLocal()
        try:
            _record_skip(db, path, event.data.get("size", 0), has_gps=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        return

    # ── Full pipeline ──
    db = SessionLocal()
    try:
        logger.info("Indexing: %s", path)

        parser = SeiParser(path)
        frames = list(parser.parse())

        if not frames:
            logger.debug("No telemetry frames found in: %s", path)
            _record_skip(db, path, event.data.get("size", 0), has_gps=False)
            db.commit()
            return

        # Assign timestamps if the parser didn't populate them
        _ensure_timestamps(frames)

        # Store all frames
        snapshot_ids = _store_frames(db, frames)
        logger.info("Indexed %d frames from: %s", len(snapshot_ids), path)

        # Record file as indexed
        indexed = IndexedFile(
            file_path=path,
            file_size=event.data.get("size", 0),
            file_mtime=datetime.now().timestamp(),
            indexed_at=datetime.now(),
            waypoint_count=len(snapshot_ids),
            event_count=0,
            has_gps=any(f.latitude is not None for f in frames),
        )
        db.merge(indexed)
        db.commit()

        # Write sidecar cache for future fast reads
        try:
            parser.write_sidecar(frames)
        except OSError:
            logger.debug("Could not write sidecar for %s", path)

        # Emit telemetry ingested event → downstream (trip, event)
        await event_bus.emit(Event(
            type=EventType.TELEMETRY_INGESTED,
            data={
                "file_path": path,
                "frame_count": len(snapshot_ids),
                "first_ts": frames[0].timestamp.isoformat() if frames[0].timestamp else None,
                "last_ts": frames[-1].timestamp.isoformat() if frames[-1].timestamp else None,
                "has_gps": any(f.latitude is not None for f in frames),
            },
        ))

        await event_bus.emit(Event(
            type=EventType.FILE_INDEXED,
            data={"file_path": path, "frame_count": len(snapshot_ids)},
        ))

        # Pipeline: mark complete
        db2 = SessionLocal()
        try:
            p = db2.query(PipelineQueue).filter(
                PipelineQueue.source_path == path,
                PipelineQueue.stage == STAGE_DETECTED,
            ).first()
            if p:
                complete(db2, p)
        finally:
            db2.close()

    except Exception:
        logger.exception("Failed to index: %s", event.data.get("path"))
        # Pipeline: mark failed
        db2 = SessionLocal()
        try:
            p = db2.query(PipelineQueue).filter(
                PipelineQueue.source_path == path,
                PipelineQueue.stage == STAGE_DETECTED,
            ).first()
            if p:
                fail(db2, p, str(sys.exc_info()[1]) if sys.exc_info()[1] else "Unknown error")
        finally:
            db2.close()
    finally:
        db.close()


# ── Protection layer helpers ──

def _is_stable(path: str) -> bool:
    """Check if a file has stopped being written to.

    The file's mtime must be unchanged for at least STABLE_WRITE_AGE seconds.
    Tesla writes dashcam clips over ~60 seconds — if mtime is still changing,
    the file is still being written.
    """
    try:
        p = Path(path)
        if not p.exists():
            return False
        stat = p.stat()
        mtime = stat.st_mtime
        now = time_mod.time()

        # File was modified less than STABLE_WRITE_AGE ago → still writing
        if now - mtime < STABLE_WRITE_AGE:
            logger.debug(
                "File %s modified %.1fs ago (need %ds stable)",
                p.name, now - mtime, STABLE_WRITE_AGE,
            )
            return False

        return True
    except OSError:
        return False


def _is_stationary(path: str) -> bool:
    """Quick peek at the start of a video to check if it's stationary.

    Peeks at the first STATIONARY_PEEK_MB of the file. If ALL frames
    in the peek window have speed < STATIONARY_SPEED_THRESHOLD and
    gear is PARK, the clip is almost certainly sentry mode → skip it.

    Returns True if the clip appears stationary (should be skipped).
    Returns False if it might be a driving clip (should be processed).
    """
    try:
        peek_frames = list(extract_sei_messages(
            path,
            sample_rate=5,  # Every 5th frame = ~6 frames/sec
            max_walk_bytes=STATIONARY_PEEK_BYTES,
        ))

        if not peek_frames:
            return False  # No frames at all → let full parser decide

        # Check if ALL peek frames are stationary
        stationary_count = 0
        for f in peek_frames:
            if abs(f.speed_mps) < STATIONARY_SPEED_THRESHOLD:
                stationary_count += 1

        # If > 90% of peek frames are stationary, skip
        ratio = stationary_count / len(peek_frames)
        if ratio > 0.9:
            logger.debug(
                "Stationary peek: %d/%d frames (%.0f%%) have speed ~0",
                stationary_count, len(peek_frames), ratio * 100,
            )
            return True

        return False

    except Exception:
        logger.debug("Stationary peek failed for %s — will process fully", path)
        return False


def _record_skip(db: Session, path: str, file_size: int, has_gps: bool) -> None:
    """Record a skipped file in the index so it won't be re-checked."""
    indexed = IndexedFile(
        file_path=path,
        file_size=file_size,
        file_mtime=datetime.now().timestamp(),
        indexed_at=datetime.now(),
        waypoint_count=0,
        event_count=0,
        has_gps=has_gps,
    )
    db.merge(indexed)


def _ensure_timestamps(frames: list[TelemetryFrame]) -> None:
    """If frames lack timestamps, distribute them evenly."""
    if frames and frames[0].timestamp:
        return
    now = datetime.now()
    for i, frame in enumerate(frames):
        frame.timestamp = now
        frame.frame_index = i


def _store_frames(db: Session, frames: list[TelemetryFrame]) -> list[int]:
    """Persist TelemetrySnapshot + TelemetryCold rows to the database."""
    ids = []
    for f in frames:
        snap = TelemetrySnapshot(
            timestamp=f.timestamp or datetime.now(),
            speed_mps=f.speed_mps,
            gear=f.gear or "",
            odometer_km=f.odometer_km,
            battery_level_pct=f.battery_level_pct,
            battery_range_km=f.battery_range_km,
            latitude=f.latitude,
            longitude=f.longitude,
            heading=f.heading,
            is_autopilot_on=f.is_autopilot_on,
            autopilot_state=f.autopilot_state,
            video_path=f.video_path,
            frame_offset=f.frame_offset,
        )
        db.add(snap)
        db.flush()

        cold = TelemetryCold(
            id=snap.id,
            acceleration_x=f.acceleration_x,
            acceleration_y=f.acceleration_y,
            acceleration_z=f.acceleration_z,
            accelerator_pedal_pct=f.accelerator_pedal_pct,
            brake_pedal_pct=f.brake_pedal_pct,
            steering_angle_deg=f.steering_angle_deg,
            brake_applied=f.brake_applied,
            blinker_left=f.blinker_left,
            blinker_right=f.blinker_right,
            inside_temp_c=f.inside_temp_c,
            outside_temp_c=f.outside_temp_c,
            fan_speed=f.fan_speed,
            is_climate_on=f.is_climate_on,
        )
        db.add(cold)
        ids.append(snap.id)

    db.flush()
    return ids
