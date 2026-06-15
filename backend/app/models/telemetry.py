"""Telemetry data models — the core input contract for all modules.

Pattern adapted from TeslaUSB's waypoints / waypoints_cold split:
- TelemetrySnapshot: frequently queried columns (time, speed, gear, GPS)
- TelemetryCold: lazy-loaded columns (acceleration, pedals, climate)
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TelemetrySnapshot(Base):
    """A single point-in-time telemetry reading.
    Equivalent to one frame of SEI data from a Tesla dashcam video.
    """

    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Time
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    # Motion (used for trip detection — always available, no GPS required)
    speed_mps: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gear: Mapped[str] = mapped_column(String(4), nullable=True)  # P, R, N, D
    odometer_km: Mapped[float] = mapped_column(Float, nullable=True)

    # Battery
    battery_level_pct: Mapped[float] = mapped_column(Float, nullable=True)
    battery_range_km: Mapped[float] = mapped_column(Float, nullable=True)
    power_kw: Mapped[float] = mapped_column(Float, nullable=True)  # + = drain, - = regen

    # GPS (optional — may be NULL when unavailable)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    heading: Mapped[int] = mapped_column(Integer, nullable=True)

    # Autopilot
    is_autopilot_on: Mapped[bool] = mapped_column(default=False)
    autopilot_state: Mapped[str] = mapped_column(String(32), nullable=True)

    # Video source
    video_path: Mapped[str] = mapped_column(String(512), nullable=True)
    frame_offset: Mapped[int] = mapped_column(Integer, nullable=True)

    # Cold data relationship (1:1, shared PK)
    cold: Mapped["TelemetryCold"] = relationship(
        back_populates="snapshot",
        uselist=False,
        lazy="selectin",
        foreign_keys="[TelemetryCold.id]",
        primaryjoin="TelemetrySnapshot.id == TelemetryCold.id",
    )

    __table_args__ = (
        Index("idx_telemetry_ts", "timestamp"),
        Index("idx_telemetry_video", "video_path", "frame_offset"),
    )


class TelemetryCold(Base):
    """Lazy-loaded telemetry data — acceleration, pedals, steering.
    Stored in a separate table (1:1) to keep the main query table lean.
    """

    __tablename__ = "telemetry_cold"

    id: Mapped[int] = mapped_column(Integer, ForeignKey("telemetry_snapshots.id"), primary_key=True)

    # Acceleration (m/s^2)
    acceleration_x: Mapped[float] = mapped_column(Float, nullable=True)
    acceleration_y: Mapped[float] = mapped_column(Float, nullable=True)
    acceleration_z: Mapped[float] = mapped_column(Float, nullable=True)

    # Driver inputs
    accelerator_pedal_pct: Mapped[float] = mapped_column(Float, nullable=True)
    brake_pedal_pct: Mapped[float] = mapped_column(Float, nullable=True)
    steering_angle_deg: Mapped[float] = mapped_column(Float, nullable=True)

    # Signals
    blinker_left: Mapped[bool] = mapped_column(default=False)
    blinker_right: Mapped[bool] = mapped_column(default=False)
    brake_applied: Mapped[bool] = mapped_column(default=False)

    # Climate
    inside_temp_c: Mapped[float] = mapped_column(Float, nullable=True)
    outside_temp_c: Mapped[float] = mapped_column(Float, nullable=True)
    fan_speed: Mapped[int] = mapped_column(Integer, nullable=True)
    is_climate_on: Mapped[bool] = mapped_column(default=False)

    snapshot: Mapped["TelemetrySnapshot"] = relationship(back_populates="cold")
