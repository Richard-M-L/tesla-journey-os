"""
Pipeline Queue Service — tracks files through the ingest pipeline.

Adapted from TeslaUSB's pipeline_queue_service.py.

Each file goes through stages:
  detected → indexing → indexed → archiving → archived

Operations:
  - enqueue: Add a file to the queue
  - claim: Claim the next pending item for a stage
  - complete: Mark an item as done, optionally enqueue for next stage
  - fail: Record failure with retry
  - recover: Reclaim stale items (worker died mid-processing)
  - dead_letter: Items that exceeded max retries

The queue lives in the 'pipeline_queue' SQLite table (model already defined).
"""

import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.file import PipelineQueue

logger = logging.getLogger("pipeline_queue")

# ── Stage constants ──
STAGE_DETECTED = "detected"
STAGE_INDEXING = "indexing"
STAGE_INDEXED = "indexed"
STAGE_ARCHIVING = "archiving"
STAGE_ARCHIVED = "archived"

# Pipeline flow: each stage → next stage
STAGE_FLOW = {
    STAGE_DETECTED: STAGE_INDEXING,
    STAGE_INDEXING: STAGE_INDEXED,
    STAGE_INDEXED: STAGE_ARCHIVING,
    STAGE_ARCHIVING: STAGE_ARCHIVED,
}

STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead_letter"

# ── Config ──
MAX_RETRIES = 3
RETRY_DELAY = 60  # seconds between retries
STALE_CLAIM_TIMEOUT = 300  # 5 min — if claimed this long, worker probably died


def enqueue(db: Session, source_path: str, stage: str = STAGE_DETECTED,
            priority: int = 5, payload: dict | None = None) -> PipelineQueue:
    """Add a file to the pipeline queue. Returns the row.

    Skips if the same (path, stage) already exists.
    """
    import json
    existing = db.query(PipelineQueue).filter(
        PipelineQueue.source_path == source_path,
        PipelineQueue.stage == stage,
    ).first()
    if existing:
        logger.debug("Already queued: %s @ %s", source_path, stage)
        return existing

    row = PipelineQueue(
        source_path=source_path,
        stage=stage,
        status=STATUS_PENDING,
        priority=priority,
        attempts=0,
        enqueued_at=time.time(),
        payload_json=json.dumps(payload) if payload else None,
    )
    db.add(row)
    db.flush()
    return row


def claim_next(db: Session, stage: str, worker_id: str = "default") -> Optional[PipelineQueue]:
    """Claim the next pending item for a stage. Returns None if queue is empty.

    Marks the item as in_progress and records the claim.
    """
    now = time.time()
    row = (
        db.query(PipelineQueue)
        .filter(
            PipelineQueue.stage == stage,
            PipelineQueue.status == STATUS_PENDING,
            (PipelineQueue.next_retry_at.is_(None)) | (PipelineQueue.next_retry_at <= now),
        )
        .order_by(PipelineQueue.priority, PipelineQueue.enqueued_at)
        .first()
    )
    if row is None:
        return None

    row.status = STATUS_IN_PROGRESS
    row.claimed_by = worker_id
    row.claimed_at = now
    row.attempts = (row.attempts or 0) + 1
    db.flush()
    return row


def complete(db: Session, row: PipelineQueue, dest_path: str | None = None) -> None:
    """Mark a pipeline item as done. Optionally enqueue for next stage."""
    row.status = STATUS_DONE
    row.completed_at = time.time()
    if dest_path:
        row.dest_path = dest_path

    # Auto-advance to next stage
    next_stage = STAGE_FLOW.get(row.stage)
    if next_stage:
        enqueue(db, row.source_path, stage=next_stage,
                priority=row.priority,
                payload={"previous_stage": row.stage, "dest_path": dest_path})

    db.flush()


def fail(db: Session, row: PipelineQueue, error: str) -> None:
    """Record a failure. Auto-retry if under max attempts.

    If max retries exceeded, move to dead_letter.
    """
    row.status = STATUS_FAILED
    row.last_error = error[:500]
    row.completed_at = time.time()

    attempts = row.attempts or 0
    if attempts < MAX_RETRIES:
        # Schedule retry
        row.next_retry_at = time.time() + (RETRY_DELAY * (2 ** (attempts - 1)))  # exponential backoff
        row.status = STATUS_PENDING  # Back to pending for retry
        logger.info("Retry %d/%d for %s in %.0fs",
                    attempts, MAX_RETRIES, row.source_path, row.next_retry_at - time.time())
    else:
        row.status = STATUS_DEAD
        logger.error("Dead letter: %s after %d attempts: %s",
                     row.source_path, attempts, error[:100])

    db.flush()


def recover_stale(db: Session, stage: str, timeout: float = STALE_CLAIM_TIMEOUT) -> int:
    """Reclaim items claimed but not completed within timeout. Returns count."""
    now = time.time()
    stale = (
        db.query(PipelineQueue)
        .filter(
            PipelineQueue.stage == stage,
            PipelineQueue.status == STATUS_IN_PROGRESS,
            PipelineQueue.claimed_at.isnot(None),
            PipelineQueue.claimed_at <= now - timeout,
        )
        .all()
    )
    for row in stale:
        # Record as failed, will be retried
        fail(db, row, f"Stale claim by {row.claimed_by} (timeout {timeout}s)")
        row.status = STATUS_PENDING  # Override fail's dead_letter — stale isn't the file's fault
        row.claimed_by = None
        row.claimed_at = None

    if stale:
        logger.warning("Recovered %d stale claims for stage '%s'", len(stale), stage)
    db.flush()
    return len(stale)


def get_queue_stats(db: Session) -> dict:
    """Get queue statistics by stage."""
    rows = (
        db.query(
            PipelineQueue.stage,
            PipelineQueue.status,
            func.count(PipelineQueue.id).label("cnt"),
        )
        .group_by(PipelineQueue.stage, PipelineQueue.status)
        .all()
    )
    stats: dict[str, dict[str, int]] = {}
    for stage, status, cnt in rows:
        if stage not in stats:
            stats[stage] = {"pending": 0, "in_progress": 0, "done": 0, "failed": 0, "dead_letter": 0}
        stats[stage][status] = cnt

    # Add dead_letter total
    dead = db.query(func.count(PipelineQueue.id)).filter(
        PipelineQueue.status == STATUS_DEAD
    ).scalar()

    return {
        "by_stage": stats,
        "total_dead_letters": dead or 0,
    }


def get_dead_letters(db: Session, limit: int = 50) -> list[dict]:
    """List dead letter items for the failed jobs UI."""
    rows = (
        db.query(PipelineQueue)
        .filter(PipelineQueue.status == STATUS_DEAD)
        .order_by(PipelineQueue.completed_at.desc())
        .limit(limit)
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def retry_dead_letter(db: Session, row_id: int) -> bool:
    """Reset a dead letter item back to pending for retry."""
    row = db.query(PipelineQueue).filter(PipelineQueue.id == row_id).first()
    if not row or row.status != STATUS_DEAD:
        return False
    row.status = STATUS_PENDING
    row.attempts = 0
    row.last_error = None
    row.next_retry_at = None
    row.claimed_by = None
    row.claimed_at = None
    db.flush()
    return True


def delete_dead_letter(db: Session, row_id: int) -> bool:
    """Permanently delete a dead letter item."""
    row = db.query(PipelineQueue).filter(PipelineQueue.id == row_id).first()
    if not row:
        return False
    db.delete(row)
    db.flush()
    return True


def _row_to_dict(row: PipelineQueue) -> dict:
    return {
        "id": row.id,
        "source_path": row.source_path,
        "dest_path": row.dest_path,
        "stage": row.stage,
        "status": row.status,
        "priority": row.priority,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "enqueued_at": row.enqueued_at,
        "completed_at": row.completed_at,
        "claimed_by": row.claimed_by,
    }
