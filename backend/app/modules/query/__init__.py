"""
Query module — read-only data access for the API layer.

All frontend data needs flow through here.
Provides clean, typed return values for:
  - Trip listing with optional filters
  - Trip detail with waypoints and events
  - Telemetry queries for charts
  - Event queries with pagination
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.models import Trip, Waypoint, DrivingEvent, TelemetrySnapshot, IndexedFile

logger = logging.getLogger("query")


# ── Trip queries ──

def list_trips(
    db: Session,
    days: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List trips, most recent first. Optionally filter to last N days."""
    q = db.query(Trip).order_by(desc(Trip.start_time))

    if days:
        since = datetime.now() - timedelta(days=days)
        q = q.filter(Trip.start_time >= since)

    trips = q.limit(limit).offset(offset).all()

    return [
        {
            "id": t.id,
            "start_time": t.start_time.isoformat(),
            "end_time": t.end_time.isoformat() if t.end_time else None,
            "distance_km": t.distance_km,
            "duration_seconds": t.duration_seconds,
            "max_speed_kmh": t.max_speed_kmh,
            "avg_speed_kmh": t.avg_speed_kmh,
            "energy_consumed_kwh": t.energy_consumed_kwh,
            "start_lat": t.start_lat,
            "start_lon": t.start_lon,
            "end_lat": t.end_lat,
            "end_lon": t.end_lon,
            "has_gps": t.start_lat is not None,
            "event_count": len(t.events) if t.events else 0,
            "waypoint_count": len(t.waypoints) if t.waypoints else 0,
        }
        for t in trips
    ]


def get_trip_detail(db: Session, trip_id: int) -> dict | None:
    """Get full trip detail with waypoints and events."""
    trip = (
        db.query(Trip)
        .options(joinedload(Trip.waypoints), joinedload(Trip.events))
        .filter(Trip.id == trip_id)
        .first()
    )

    if not trip:
        return None

    return {
        "id": trip.id,
        "start_time": trip.start_time.isoformat(),
        "end_time": trip.end_time.isoformat() if trip.end_time else None,
        "distance_km": trip.distance_km,
        "duration_seconds": trip.duration_seconds,
        "max_speed_kmh": trip.max_speed_kmh,
        "avg_speed_kmh": trip.avg_speed_kmh,
        "energy_consumed_kwh": trip.energy_consumed_kwh,
        "source": trip.source,
        "has_gps": trip.start_lat is not None,
        "start_lat": trip.start_lat,
        "start_lon": trip.start_lon,
        "end_lat": trip.end_lat,
        "end_lon": trip.end_lon,
        "waypoints": [
            {
                "id": wp.id,
                "timestamp": wp.timestamp.isoformat(),
                "latitude": wp.latitude,
                "longitude": wp.longitude,
                "heading": wp.heading,
                "speed_mps": wp.speed_mps,
                "autopilot_state": wp.autopilot_state,
                "gap_after": wp.gap_after,
            }
            for wp in (trip.waypoints or [])
        ],
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "event_type": e.event_type,
                "severity": e.severity,
                "description": e.description,
                "latitude": e.latitude,
                "longitude": e.longitude,
                "video_path": e.video_path,
                "frame_offset": e.frame_offset,
            }
            for e in (trip.events or [])
        ],
    }


# ── Event queries ──

def list_events(
    db: Session,
    event_type: str | None = None,
    severity: str | None = None,
    trip_id: int | None = None,
    days: int | None = 30,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List events with optional filters."""
    q = db.query(DrivingEvent).order_by(desc(DrivingEvent.timestamp))

    if event_type:
        q = q.filter(DrivingEvent.event_type == event_type)
    if severity:
        q = q.filter(DrivingEvent.severity == severity)
    if trip_id:
        q = q.filter(DrivingEvent.trip_id == trip_id)
    if days:
        since = datetime.now() - timedelta(days=days)
        q = q.filter(DrivingEvent.timestamp >= since)

    events = q.limit(limit).offset(offset).all()

    return [
        {
            "id": e.id,
            "trip_id": e.trip_id,
            "timestamp": e.timestamp.isoformat(),
            "event_type": e.event_type,
            "severity": e.severity,
            "description": e.description,
            "latitude": e.latitude,
            "longitude": e.longitude,
            "has_gps": e.latitude is not None,
            "video_path": e.video_path,
            "frame_offset": e.frame_offset,
        }
        for e in events
    ]


# ── Telemetry queries ──

def get_telemetry_for_trip(
    db: Session,
    trip_id: int,
    sample_rate: int = 30,
) -> list[dict]:
    """Get telemetry snapshots for a trip, decimated to the given sample rate."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        return []

    snaps = (
        db.query(TelemetrySnapshot)
        .filter(
            TelemetrySnapshot.timestamp >= trip.start_time,
            TelemetrySnapshot.timestamp <= trip.end_time,
        )
        .order_by(TelemetrySnapshot.timestamp)
        .all()
    )

    result = []
    for i, s in enumerate(snaps):
        if i % sample_rate != 0:
            continue
        result.append({
            "timestamp": s.timestamp.isoformat(),
            "speed_mps": s.speed_mps,
            "speed_kmh": round(s.speed_mps * 3.6, 1),
            "gear": s.gear,
            "odometer_km": s.odometer_km,
            "battery_level_pct": s.battery_level_pct,
            "battery_range_km": s.battery_range_km,
            "power_kw": s.power_kw,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "heading": s.heading,
            "is_autopilot_on": s.is_autopilot_on,
            "autopilot_state": s.autopilot_state,
            "video_path": s.video_path,
            "frame_offset": s.frame_offset,
            "has_gps": s.latitude is not None,
        })
    return result


# ── Stats / Overview ──

def get_stats_overview(db: Session) -> dict:
    """Return a summary of all data in the system."""
    trip_count = db.query(func.count(Trip.id)).scalar()
    event_count = db.query(func.count(DrivingEvent.id)).scalar()
    telemetry_count = db.query(func.count(TelemetrySnapshot.id)).scalar()
    file_count = db.query(func.count(IndexedFile.file_path)).scalar()

    total_distance = db.query(func.coalesce(func.sum(Trip.distance_km), 0)).scalar()
    total_duration = db.query(func.coalesce(func.sum(Trip.duration_seconds), 0)).scalar()

    gps_trips = db.query(func.count(Trip.id)).filter(Trip.start_lat.isnot(None)).scalar()
    gps_pct = round((gps_trips / trip_count) * 100, 1) if trip_count else 0

    return {
        "total_trips": trip_count,
        "total_events": event_count,
        "total_telemetry_snapshots": telemetry_count,
        "total_indexed_files": file_count,
        "total_distance_km": round(total_distance, 1),
        "total_duration_hours": round(total_duration / 3600, 1),
        "trips_with_gps_pct": gps_pct,
        "trips_without_gps_pct": round(100 - gps_pct, 1),
    }


def get_trips_by_day(db: Session, days: int = 30) -> list[dict]:
    """Get trip counts grouped by day for timeline charts."""
    since = datetime.now() - timedelta(days=days)

    rows = (
        db.query(
            func.date(Trip.start_time).label("day"),
            func.count(Trip.id).label("count"),
            func.coalesce(func.sum(Trip.distance_km), 0).label("distance"),
            func.coalesce(func.sum(Trip.duration_seconds), 0).label("duration"),
        )
        .filter(Trip.start_time >= since)
        .group_by(func.date(Trip.start_time))
        .order_by("day")
        .all()
    )

    return [
        {
            "date": row.day,
            "trip_count": row.count,
            "distance_km": round(row.distance, 1),
            "duration_hours": round(row.duration / 3600, 1),
        }
        for row in rows
    ]
