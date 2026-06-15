"""Geo resolution cache — offline address lookup results."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GeoCache(Base):
    """Cached reverse-geocoding results.

    Since this is a local-first system, we cache lookups to avoid
    repeated API calls when GPS is available.
    """

    __tablename__ = "geo_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    # Resolved address components
    address: Mapped[str] = mapped_column(String(512), nullable=True)
    city: Mapped[str] = mapped_column(String(128), nullable=True)
    province: Mapped[str] = mapped_column(String(128), nullable=True)
    country: Mapped[str] = mapped_column(String(64), nullable=True)

    resolved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_geo_coords", "latitude", "longitude", unique=True),
    )
