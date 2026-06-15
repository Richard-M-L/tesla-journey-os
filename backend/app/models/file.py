"""File indexing models — track which files have been processed."""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IndexedFile(Base):
    """Tracks processed video files to avoid re-indexing."""

    __tablename__ = "indexed_files"

    file_path: Mapped[str] = mapped_column(String(512), primary_key=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_mtime: Mapped[float] = mapped_column(Float, default=0.0)
    indexed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    waypoint_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    has_gps: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("idx_indexed_files_mtime", "file_mtime"),
    )


class PipelineQueue(Base):
    """Unified work queue for inter-module coordination.

    Adapted from TeslaUSB's pipeline_queue table.
    Stages: ingest -> index -> archive -> cloud
    """

    __tablename__ = "pipeline_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(String(512), nullable=False)
    dest_path: Mapped[str] = mapped_column(String(512), nullable=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[float] = mapped_column(Float, nullable=True)
    enqueued_at: Mapped[float] = mapped_column(Float, default=0.0)
    completed_at: Mapped[float] = mapped_column(Float, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_pipeline_ready", "stage", "status", "next_retry_at"),
        Index("idx_pipeline_source", "source_path", "stage", unique=True),
    )
