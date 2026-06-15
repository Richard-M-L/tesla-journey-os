"""
Event Engine — detects driving behavior events from telemetry data.

Six event types detected per-frame:
  - emergency_brake   (longitudinal accel <= -7.0 m/s^2)
  - harsh_brake       (longitudinal accel <= -4.0 m/s^2)
  - hard_acceleration (longitudinal accel >= +3.5 m/s^2)
  - sharp_turn        (lateral |accel| >= 4.0 m/s^2)
  - speeding          (speed > 35.76 m/s)
  - autopilot_disengage (autopilot state transition to NONE)

Adapted from TeslaUSB's mapping_service.py::_detect_events().
GPS is OPTIONAL — all events work with telemetry alone.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.config import config
from app.event_bus import Event, EventType, event_bus
from app.models import Trip, DrivingEvent, TelemetrySnapshot, TelemetryCold

logger = logging.getLogger("event_engine")


async def register() -> None:
    """Register event engine listeners on the event bus."""
    event_bus.subscribe(EventType.TELEMETRY_INGESTED, on_telemetry_ingested)


async def on_telemetry_ingested(event: Event) -> None:
    """After telemetry is ingested, detect driving events in the new data."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        data = event.data
        first_ts = data["first_ts"]
        last_ts = data["last_ts"]

        if not first_ts or not last_ts:
            return

        new_events = _detect_events_in_range(db, first_ts, last_ts)

        if new_events:
            db.commit()
            for evt in new_events:
                logger.info("Event detected: %s at %s", evt.event_type, evt.timestamp)
                await event_bus.emit(Event(
                    type=EventType.EVENT_DETECTED,
                    data={
                        "event_id": evt.id,
                        "event_type": evt.event_type,
                        "severity": evt.severity,
                        "trip_id": evt.trip_id,
                        "timestamp": evt.timestamp.isoformat(),
                    },
                ))

    except Exception:
        logger.exception("Event detection failed")
        db.rollback()
    finally:
        db.close()


def _detect_events_in_range(db: Session, first_ts: str, last_ts: str) -> list[DrivingEvent]:
    """Detect driving events in a time range of telemetry snapshots."""
    from datetime import datetime

    # Load snapshots with cold data in the range
    snaps = (
        db.query(TelemetrySnapshot)
        .filter(
            TelemetrySnapshot.timestamp >= datetime.fromisoformat(first_ts),
            TelemetrySnapshot.timestamp <= datetime.fromisoformat(last_ts),
        )
        .order_by(TelemetrySnapshot.timestamp)
        .all()
    )

    if not snaps:
        return []

    # Load cold data for all snaps in one query
    snap_ids = [s.id for s in snaps]
    cold_map = {
        c.id: c
        for c in db.query(TelemetryCold).filter(TelemetryCold.id.in_(snap_ids)).all()
    }

    # Find the trip for this time range
    trip = (
        db.query(Trip)
        .filter(Trip.start_time <= snaps[-1].timestamp, Trip.end_time >= snaps[0].timestamp)
        .first()
    )

    events: list[DrivingEvent] = []
    cfg = config.events

    for i, snap in enumerate(snaps):
        cold = cold_map.get(snap.id)
        if not cold:
            continue

        prev_snap = snaps[i - 1] if i > 0 else None

        # ── Acceleration-based events ──
        if cold.acceleration_x is not None:
            event = _check_accel_event(snap, cold, prev_snap, trip, cfg)
            if event:
                events.append(event)
                db.add(event)

        # ── Sharp turn (lateral acceleration) ──
        if cfg.sharp_turn.enabled and cold.acceleration_y is not None:
            if abs(cold.acceleration_y) >= cfg.sharp_turn.threshold_ms2:
                events.append(DrivingEvent(
                    trip_id=trip.id if trip else None,
                    timestamp=snap.timestamp,
                    latitude=snap.latitude,
                    longitude=snap.longitude,
                    event_type="sharp_turn",
                    severity="warning",
                    description=f"Sharp turn: {cold.acceleration_y:.1f} m/s^2 lateral",
                    video_path=snap.video_path,
                    frame_offset=snap.frame_offset,
                ))

        # ── Speeding ──
        if cfg.speeding.get("enabled", True):
            threshold = cfg.speeding.get("threshold_mps", 35.76)
            if snap.speed_mps > threshold:
                events.append(DrivingEvent(
                    trip_id=trip.id if trip else None,
                    timestamp=snap.timestamp,
                    latitude=snap.latitude,
                    longitude=snap.longitude,
                    event_type="speeding",
                    severity="info",
                    description=f"Speeding: {snap.speed_mps * 3.6:.0f} km/h",
                    video_path=snap.video_path,
                    frame_offset=snap.frame_offset,
                ))

        # ── Autopilot disengage ──
        if cfg.autopilot_disengage.get("enabled", True) and prev_snap:
            prev_state = prev_snap.autopilot_state or ""
            curr_state = snap.autopilot_state or ""
            if prev_state in ("SELF_DRIVING", "AUTOSTEER") and curr_state == "NONE":
                events.append(DrivingEvent(
                    trip_id=trip.id if trip else None,
                    timestamp=snap.timestamp,
                    latitude=snap.latitude,
                    longitude=snap.longitude,
                    event_type="autopilot_disengage",
                    severity="warning",
                    description="Autopilot disengaged",
                    video_path=snap.video_path,
                    frame_offset=snap.frame_offset,
                ))

        # ── Battery low ──
        if cfg.battery_low.get("enabled", True):
            threshold = cfg.battery_low.get("threshold_pct", 10)
            if snap.battery_level_pct is not None and snap.battery_level_pct <= threshold:
                events.append(DrivingEvent(
                    trip_id=trip.id if trip else None,
                    timestamp=snap.timestamp,
                    latitude=snap.latitude,
                    longitude=snap.longitude,
                    event_type="battery_low",
                    severity="warning",
                    description=f"Battery low: {snap.battery_level_pct:.0f}%",
                    video_path=snap.video_path,
                    frame_offset=snap.frame_offset,
                ))

    return events


def _check_accel_event(
    snap: TelemetrySnapshot,
    cold: TelemetryCold,
    prev_snap: TelemetrySnapshot | None,
    trip: Trip | None,
    cfg,
) -> DrivingEvent | None:
    """Check for acceleration-based events (emergency brake, harsh brake, hard accel)."""
    accel = cold.acceleration_x
    if accel is None:
        return None

    # Emergency brake
    if cfg.emergency_brake.enabled and accel <= cfg.emergency_brake.threshold_ms2:
        return DrivingEvent(
            trip_id=trip.id if trip else None,
            timestamp=snap.timestamp,
            latitude=snap.latitude,
            longitude=snap.longitude,
            event_type="emergency_brake",
            severity="critical",
            description=f"Emergency brake: {accel:.1f} m/s^2",
            video_path=snap.video_path,
            frame_offset=snap.frame_offset,
            metadata_json=json.dumps({"acceleration_x": accel}),
        )

    # Harsh brake
    if cfg.harsh_brake.enabled and accel <= cfg.harsh_brake.threshold_ms2:
        return DrivingEvent(
            trip_id=trip.id if trip else None,
            timestamp=snap.timestamp,
            latitude=snap.latitude,
            longitude=snap.longitude,
            event_type="harsh_brake",
            severity="warning",
            description=f"Harsh brake: {accel:.1f} m/s^2",
            video_path=snap.video_path,
            frame_offset=snap.frame_offset,
            metadata_json=json.dumps({"acceleration_x": accel}),
        )

    # Hard acceleration
    if cfg.hard_acceleration.enabled and accel >= cfg.hard_acceleration.threshold_ms2:
        return DrivingEvent(
            trip_id=trip.id if trip else None,
            timestamp=snap.timestamp,
            latitude=snap.latitude,
            longitude=snap.longitude,
            event_type="hard_acceleration",
            severity="info",
            description=f"Hard acceleration: {accel:.1f} m/s^2",
            video_path=snap.video_path,
            frame_offset=snap.frame_offset,
            metadata_json=json.dumps({"acceleration_x": accel}),
        )

    return None
