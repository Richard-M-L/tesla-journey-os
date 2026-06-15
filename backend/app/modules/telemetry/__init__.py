"""
Telemetry module — processes raw telemetry frames into stored snapshots.

This is the central ingest pipeline:
  1. Listens for FILE_DETECTED events
  2. Parses SEI data from MP4 files
  3. Stores TelemetrySnapshot + TelemetryCold rows
  4. Emits TELEMETRY_INGESTED events for downstream modules
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.event_bus import Event, EventType, event_bus
from app.models import IndexedFile, TelemetrySnapshot, TelemetryCold
from app.modules.ingestion.parser import SeiParser, TelemetryFrame

logger = logging.getLogger("telemetry")


async def register() -> None:
    """Register telemetry event listeners on the event bus."""
    event_bus.subscribe(EventType.FILE_DETECTED, on_file_detected)


async def on_file_detected(event: Event) -> None:
    """Handle a new file detection — parse and store its telemetry."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        path = event.data["path"]
        logger.info("Indexing: %s", path)

        parser = SeiParser(path)
        frames = list(parser.parse())

        if not frames:
            logger.debug("No telemetry frames found in: %s", path)
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

        # Emit telemetry ingested event for each frame batch
        # Downstream modules (trip, event) listen for this
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

        # Emit file indexed event
        await event_bus.emit(Event(
            type=EventType.FILE_INDEXED,
            data={"file_path": path, "frame_count": len(snapshot_ids)},
        ))

    except Exception:
        logger.exception("Failed to index: %s", event.data.get("path"))
    finally:
        db.close()


def _ensure_timestamps(frames: list[TelemetryFrame]) -> None:
    """If frames lack timestamps, distribute them evenly across the file's duration.
    Tesla dashcam files are 60 seconds at 30 fps = 1800 frames max.
    """
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
        db.flush()  # Get the snapshot ID

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
