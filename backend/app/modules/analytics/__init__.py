"""
Analytics Engine — pre-computed statistics for the dashboard.

Provides:
  - Trip summaries (count, total distance, total duration)
  - Event distributions (by type, by severity)
  - Driving behavior scores
  - Battery efficiency trends

All analytics work without GPS.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Trip, DrivingEvent, TelemetrySnapshot

logger = logging.getLogger("analytics_engine")


def get_trip_summary(db: Session, days: int = 30) -> dict:
    """Aggregate trip statistics for the past N days."""
    since = datetime.now() - timedelta(days=days)

    trips = db.query(Trip).filter(Trip.start_time >= since).all()

    total_distance = sum(t.distance_km or 0 for t in trips)
    total_duration = sum(t.duration_seconds or 0 for t in trips)
    total_energy = sum(t.energy_consumed_kwh or 0 for t in trips)

    return {
        "period_days": days,
        "trip_count": len(trips),
        "total_distance_km": round(total_distance, 1),
        "total_duration_hours": round(total_duration / 3600, 1),
        "total_energy_kwh": round(total_energy, 1),
        "avg_distance_per_trip_km": round(total_distance / len(trips), 1) if trips else 0,
        "avg_efficiency_wh_per_km": round(
            (total_energy * 1000) / total_distance, 1
        ) if total_distance > 0 else 0,
    }


def get_event_distribution(db: Session, days: int = 30) -> dict:
    """Count events by type for the past N days."""
    since = datetime.now() - timedelta(days=days)

    rows = (
        db.query(
            DrivingEvent.event_type,
            DrivingEvent.severity,
            func.count(DrivingEvent.id).label("cnt"),
        )
        .filter(DrivingEvent.timestamp >= since)
        .group_by(DrivingEvent.event_type, DrivingEvent.severity)
        .all()
    )

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for row in rows:
        by_type[row.event_type] = by_type.get(row.event_type, 0) + row.cnt
        by_severity[row.severity] = by_severity.get(row.severity, 0) + row.cnt

    return {
        "period_days": days,
        "total_events": sum(by_type.values()),
        "by_type": by_type,
        "by_severity": by_severity,
    }


def get_driving_score(db: Session, days: int = 30) -> dict:
    """Compute a simple driving behavior score (0–100).

    Deductions come from harsh events per 100 km. A lower events/km ratio
    means a better (higher) score.
    """
    summary = get_trip_summary(db, days)
    dist = summary["total_distance_km"]

    if dist < 1:
        return {"score": None, "reason": "Not enough driving data"}

    event_dist = get_event_distribution(db, days)
    harsh_events = sum(
        event_dist["by_type"].get(t, 0)
        for t in ("harsh_brake", "emergency_brake", "sharp_turn")
    )

    # Deduction: 5 points per harsh event per 100 km
    events_per_100km = (harsh_events / dist) * 100
    deduction = min(events_per_100km * 5, 100)
    score = max(round(100 - deduction), 0)

    return {
        "score": score,
        "total_harsh_events": harsh_events,
        "events_per_100km": round(events_per_100km, 1),
        "distance_km": round(dist, 1),
        "period_days": days,
    }


def get_speed_profile(db: Session, trip_id: int) -> list[dict]:
    """Get a speed-over-time profile for a single trip."""
    snaps = (
        db.query(TelemetrySnapshot)
        .join(Trip, TelemetrySnapshot.timestamp.between(Trip.start_time, Trip.end_time))
        .filter(Trip.id == trip_id)
        .order_by(TelemetrySnapshot.timestamp)
        .all()
    )

    return [
        {
            "timestamp": s.timestamp.isoformat(),
            "speed_kmh": round(s.speed_mps * 3.6, 1),
            "power_kw": s.power_kw,
            "is_autopilot_on": s.is_autopilot_on,
        }
        for s in snaps
    ]


def get_battery_trend(db: Session, days: int = 30) -> list[dict]:
    """Get battery level trend over time."""
    since = datetime.now() - timedelta(days=days)

    # Sample one reading per hour
    snaps = (
        db.query(TelemetrySnapshot)
        .filter(
            TelemetrySnapshot.timestamp >= since,
            TelemetrySnapshot.battery_level_pct.isnot(None),
        )
        .order_by(TelemetrySnapshot.timestamp)
        .all()
    )

    # Decimate to ~1 reading per hour
    trend = []
    last_hour = -1
    for s in snaps:
        hour = s.timestamp.hour + s.timestamp.day * 24
        if hour != last_hour and s.battery_level_pct is not None:
            trend.append({
                "timestamp": s.timestamp.isoformat(),
                "battery_pct": round(s.battery_level_pct, 1),
                "range_km": round(s.battery_range_km, 1) if s.battery_range_km else None,
            })
            last_hour = hour

    return trend
