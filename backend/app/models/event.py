"""Detected driving events — harsh braking, hard acceleration, etc."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DrivingEvent(Base):
    """A driving behavior event detected from telemetry analysis.

    Events are detected per-frame from acceleration, speed, and autopilot state.
    GPS is optional — events work fully with telemetry data alone.
    """

    __tablename__ = "driving_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trip_id: Mapped[int] = mapped_column(Integer, ForeignKey("trips.id", ondelete="CASCADE"))

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # GPS (optional)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)

    # Event classification
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # info, warning, critical
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Source
    video_path: Mapped[str] = mapped_column(String(512), nullable=True)
    frame_offset: Mapped[int] = mapped_column(Integer, nullable=True)

    # Extra data as JSON string
    metadata_json: Mapped[str] = mapped_column(Text, nullable=True)

    trip: Mapped["Trip"] = relationship(back_populates="events")

    __table_args__ = (
        Index("idx_events_trip", "trip_id"),
        Index("idx_events_type", "event_type"),
        Index("idx_events_ts", "trip_id", "timestamp"),
    )
