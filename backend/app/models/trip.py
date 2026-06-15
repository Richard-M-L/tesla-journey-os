"""Trip and Waypoint models — trip detection relies on telemetry, not GPS."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Trip(Base):
    """A driving session identified from telemetry patterns.

    Trip boundaries are detected from speed, gear state, and timestamps.
    GPS coordinates are optional — trips work fully without them.
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Time boundaries
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # GPS (optional — both NULL when unavailable)
    start_lat: Mapped[float] = mapped_column(Float, nullable=True)
    start_lon: Mapped[float] = mapped_column(Float, nullable=True)
    end_lat: Mapped[float] = mapped_column(Float, nullable=True)
    end_lon: Mapped[float] = mapped_column(Float, nullable=True)

    # Computed stats
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    max_speed_kmh: Mapped[float] = mapped_column(Float, nullable=True)
    avg_speed_kmh: Mapped[float] = mapped_column(Float, nullable=True)
    energy_consumed_kwh: Mapped[float] = mapped_column(Float, nullable=True)

    # Metadata
    source: Mapped[str] = mapped_column(String(32), default="telemetry")
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    waypoints: Mapped[list["Waypoint"]] = relationship(back_populates="trip", lazy="selectin")
    events: Mapped[list["DrivingEvent"]] = relationship(back_populates="trip", lazy="selectin")

    __table_args__ = (
        Index("idx_trips_start_time", "start_time"),
        Index("idx_trips_end_time", "end_time"),
    )


class Waypoint(Base):
    """A sampled point within a trip — lightweight, used for map rendering.

    Unlike TelemetrySnapshot (which stores raw high-frequency data),
    Waypoints are decimated samples for efficient map display.
    """

    __tablename__ = "waypoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(Integer, ForeignKey("trips.id", ondelete="CASCADE"))

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    heading: Mapped[int] = mapped_column(Integer, nullable=True)
    speed_mps: Mapped[float] = mapped_column(Float, nullable=True)
    autopilot_state: Mapped[str] = mapped_column(String(32), nullable=True)
    gap_after: Mapped[bool] = mapped_column(default=False)

    trip: Mapped["Trip"] = relationship(back_populates="waypoints")

    __table_args__ = (
        Index("idx_waypoints_trip", "trip_id"),
        Index("idx_waypoints_ts", "trip_id", "timestamp"),
    )
