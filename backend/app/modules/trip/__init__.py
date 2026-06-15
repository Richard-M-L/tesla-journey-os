"""
Trip Engine — detects trip boundaries from telemetry patterns.

Core principle: GPS is NEVER required for trip detection.
Trips are identified from:
  - Speed transitions (0 → moving → 0)
  - Gear state changes (P → D → P)
  - Time gaps between consecutive telemetry (gap > threshold = new trip)

Adapted from TeslaUSB's mapping_service.py trip detection logic,
but simplified to pure telemetry (no GPS dependency).
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import config
from app.event_bus import Event, EventType, event_bus
from app.models import Trip, TelemetrySnapshot

logger = logging.getLogger("trip_engine")

# Sentinel gap — two waypoints farther apart than this (in seconds) split a trip
GAP_SECONDS = config.trip.gap_minutes * 60
MIN_DURATION = config.trip.min_duration_seconds
MIN_DISTANCE = config.trip.min_distance_km
STATIONARY_SPEED = config.trip.stationary_speed_mps
STATIONARY_TIMEOUT = config.trip.stationary_timeout_seconds


async def register() -> None:
    """Register trip engine listeners on the event bus."""
    event_bus.subscribe(EventType.TELEMETRY_INGESTED, on_telemetry_ingested)


async def on_telemetry_ingested(event: Event) -> None:
    """After telemetry is ingested, detect and update trips.

    This runs the trip detection algorithm:
      1. Find the time range of the newly ingested data
      2. Look for an existing trip that overlaps or is within GAP_SECONDS
      3. If found, extend the trip. If not, create a new trip.
      4. Check for adjacent trip merges.
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        data = event.data
        first_ts = datetime.fromisoformat(data["first_ts"])
        last_ts = datetime.fromisoformat(data["last_ts"])

        # 1. Find or create a trip for this time window
        trip = _find_or_create_trip(db, first_ts, last_ts)

        # 2. Generate waypoints for the trip from snapshots in range
        _generate_waypoints(db, trip, first_ts, last_ts)

        # 3. Recompute trip stats
        _recompute_trip_stats(db, trip)

        # 4. Check for merges with adjacent trips
        _merge_adjacent_trips(db, trip)

        db.commit()

        # Emit trip lifecycle events
        if trip.duration_seconds is not None and trip.duration_seconds > 0:
            await event_bus.emit(Event(
                type=EventType.TRIP_UPDATED,
                data={"trip_id": trip.id, "start_time": trip.start_time.isoformat(),
                      "end_time": trip.end_time.isoformat() if trip.end_time else None},
            ))

    except Exception:
        logger.exception("Trip detection failed for telemetry batch")
        db.rollback()
    finally:
        db.close()


def _find_or_create_trip(db: Session, first_ts: datetime, last_ts: datetime) -> Trip:
    """Find an existing trip within gap threshold, or create a new one.

    Query logic (adapted from TeslaUSB's trip matching SQL):
      Find trips where (new_start - trip_end) <= gap AND (trip_start - new_end) <= gap
      This catches both overlapping and near-miss trips.
    """
    gap = timedelta(seconds=GAP_SECONDS)

    # Find the best-matching existing trip
    existing = (
        db.query(Trip)
        .filter(
            Trip.start_time.isnot(None),
            Trip.end_time.isnot(None),
            func.julianday(first_ts) - func.julianday(Trip.end_time) <= gap.total_seconds() / 86400,
            func.julianday(Trip.start_time) - func.julianday(last_ts) <= gap.total_seconds() / 86400,
        )
        .order_by(
            # Prefer the trip with the smallest temporal gap
            func.abs(func.julianday(first_ts) - func.julianday(Trip.end_time))
        )
        .first()
    )

    if existing:
        logger.debug("Extending trip %d: %s → %s", existing.id, existing.start_time, last_ts)
        if first_ts < existing.start_time:
            existing.start_time = first_ts
        if last_ts > existing.end_time:
            existing.end_time = last_ts
        return existing

    # No matching trip — create a new one
    trip = Trip(start_time=first_ts, end_time=last_ts, source="telemetry")
    db.add(trip)
    db.flush()

    logger.info("New trip %d: %s → %s", trip.id, first_ts, last_ts)
    return trip


def _generate_waypoints(db: Session, trip: Trip, first_ts: datetime, last_ts: datetime) -> None:
    """Decimate telemetry snapshots into waypoints for the trip.

    Waypoints are a sampled subset of telemetry snapshots, optimized for
    map rendering and trip overview display.
    """
    from app.models import Waypoint

    # Delete existing waypoints in this time range to avoid duplicates
    db.query(Waypoint).filter(
        Waypoint.trip_id == trip.id,
        Waypoint.timestamp >= first_ts,
        Waypoint.timestamp <= last_ts,
    ).delete()

    # Sample snapshots at ~1 Hz (every 30th frame at 30 fps)
    sample_rate = 30
    snaps = (
        db.query(TelemetrySnapshot)
        .filter(
            TelemetrySnapshot.timestamp >= first_ts,
            TelemetrySnapshot.timestamp <= last_ts,
        )
        .order_by(TelemetrySnapshot.timestamp)
        .all()
    )

    prev_snap: TelemetrySnapshot | None = None
    for i, snap in enumerate(snaps):
        if i % sample_rate != 0:
            continue

        # Detect gaps between this waypoint and the previous one
        gap_after = False
        if prev_snap:
            time_gap = (snap.timestamp - prev_snap.timestamp).total_seconds()
            gap_after = time_gap > 60  # 60-second gap = break in polyline

        wp = Waypoint(
            trip_id=trip.id,
            timestamp=snap.timestamp,
            latitude=snap.latitude,
            longitude=snap.longitude,
            heading=snap.heading,
            speed_mps=snap.speed_mps,
            autopilot_state=snap.autopilot_state,
            gap_after=gap_after,
        )
        db.add(wp)
        prev_snap = snap


def _recompute_trip_stats(db: Session, trip: Trip) -> None:
    """Recalculate trip distance, duration, and speed stats from waypoints."""
    from math import asin, cos, radians, sin, sqrt

    from app.models import Waypoint

    waypoints = (
        db.query(Waypoint)
        .filter(Waypoint.trip_id == trip.id)
        .order_by(Waypoint.timestamp)
        .all()
    )

    if not waypoints:
        return

    trip.start_time = waypoints[0].timestamp
    trip.end_time = waypoints[-1].timestamp

    duration = (trip.end_time - trip.start_time).total_seconds()
    trip.duration_seconds = int(duration) if duration > 0 else 0

    # Compute distance: prefer GPS (Haversine), fall back to speed×time integration
    gps_km = 0.0
    telemetry_km = 0.0
    max_speed = 0.0
    speed_sum = 0.0
    speed_count = 0
    has_gps = False

    for i in range(1, len(waypoints)):
        prev = waypoints[i - 1]
        curr = waypoints[i]

        # GPS distance (Haversine)
        if prev.latitude is not None and curr.latitude is not None:
            d = _haversine(prev.latitude, prev.longitude or 0,
                          curr.latitude, curr.longitude or 0)
            gps_km += d
            has_gps = True

        # Telemetry distance: speed × time between waypoints
        if curr.speed_mps is not None and prev.timestamp and curr.timestamp:
            dt = (curr.timestamp - prev.timestamp).total_seconds()
            if dt > 0:
                avg_speed = (curr.speed_mps + (prev.speed_mps or 0)) / 2
                telemetry_km += avg_speed * dt / 1000.0  # m/s * s → km

        if curr.speed_mps is not None:
            max_speed = max(max_speed, curr.speed_mps)
            speed_sum += curr.speed_mps
            speed_count += 1

    # Use GPS distance when available, otherwise fall back to telemetry estimation
    trip.distance_km = round(max(gps_km if has_gps else telemetry_km, 0), 3)
    trip.max_speed_kmh = round(max_speed * 3.6, 1) if max_speed > 0 else None
    trip.avg_speed_kmh = round((speed_sum / speed_count) * 3.6, 1) if speed_count > 0 else None

    # Set GPS endpoints from first/last waypoints with coordinates
    for wp in waypoints:
        if wp.latitude is not None:
            trip.start_lat = wp.latitude
            trip.start_lon = wp.longitude
            break

    for wp in reversed(waypoints):
        if wp.latitude is not None:
            trip.end_lat = wp.latitude
            trip.end_lon = wp.longitude
            break


def _merge_adjacent_trips(db: Session, trip: Trip) -> None:
    """Check if this trip now bridges to an adjacent trip and merge them.

    Adapted from TeslaUSB's _merge_adjacent_trips_for().
    Two trips whose endpoints are within GAP_SECONDS get merged:
    the lower-ID trip survives and absorbs the higher-ID trip.
    """
    from app.models import Waypoint

    gap = GAP_SECONDS / 86400.0  # Convert to days for SQLite julianday

    # Find trips that are now adjacent to this one
    adjacent = (
        db.query(Trip)
        .filter(
            Trip.id != trip.id,
            Trip.end_time.isnot(None),
            Trip.start_time.isnot(None),
            # Adjacency: end of one is within gap of start of another
            func.abs(func.julianday(trip.end_time) - func.julianday(Trip.start_time)) <= gap,
        )
        .all()
    )

    for other in adjacent:
        keeper = trip if trip.id < other.id else other
        absorbed = other if trip.id < other.id else trip

        logger.info("Merging trip %d into trip %d", absorbed.id, keeper.id)

        # Repoint waypoints
        db.query(Waypoint).filter(Waypoint.trip_id == absorbed.id).update(
            {Waypoint.trip_id: keeper.id}
        )
        # Repoint events
        from app.models import DrivingEvent
        db.query(DrivingEvent).filter(DrivingEvent.trip_id == absorbed.id).update(
            {DrivingEvent.trip_id: keeper.id}
        )

        # Extend keeper's time range
        keeper.start_time = min(keeper.start_time, absorbed.start_time)
        keeper.end_time = max(keeper.end_time or keeper.start_time,
                             absorbed.end_time or absorbed.start_time)

        # Delete the absorbed trip
        db.delete(absorbed)
        db.flush()

        # Recompute stats for the merged trip
        _recompute_trip_stats(db, keeper)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute the great-circle distance in kilometers between two GPS coordinates."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371.0  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * asin(sqrt(a))
