"""
Storage Engine — database maintenance and health checks.

Provides:
  - WAL checkpointing (periodic)
  - Database file size monitoring
  - Health check endpoint data
"""

import logging
import os

from app.config import config

logger = logging.getLogger("storage_engine")


def get_database_size() -> dict[str, int]:
    """Return the file sizes of both databases in bytes."""
    db_path = config.storage.database_path
    geo_path = config.storage.geodata_path

    result = {"tjos_db_bytes": 0, "geodata_db_bytes": 0}

    if os.path.exists(db_path):
        result["tjos_db_bytes"] = os.path.getsize(db_path)
    if os.path.exists(geo_path):
        result["geodata_db_bytes"] = os.path.getsize(geo_path)

    return result


def get_wal_size() -> dict[str, int]:
    """Return the WAL file sizes for both databases."""
    result = {"tjos_wal_bytes": 0, "geodata_wal_bytes": 0}

    for name, path in [("tjos_wal_bytes", config.storage.database_path + "-wal"),
                       ("geodata_wal_bytes", config.storage.geodata_path + "-wal")]:
        if os.path.exists(path):
            result[name] = os.path.getsize(path)

    return result


async def run_checkpoint() -> bool:
    """Execute a WAL checkpoint on all databases.

    Returns True if successful. Running this periodically prevents
    WAL files from growing unbounded.
    """
    from app.database import engine

    try:
        with engine.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        logger.debug("WAL checkpoint completed")
        return True
    except Exception:
        logger.exception("WAL checkpoint failed")
        return False


def get_storage_health() -> dict:
    """Return a health summary for the storage layer."""
    db_size = get_database_size()
    wal_size = get_wal_size()

    total_db = db_size["tjos_db_bytes"] + db_size["geodata_db_bytes"]
    total_wal = wal_size["tjos_wal_bytes"] + wal_size["geodata_wal_bytes"]

    # WAL should be < 10% of DB size
    wal_ratio = total_wal / total_db if total_db > 0 else 0
    healthy = wal_ratio < 0.1

    return {
        "healthy": healthy,
        "database_size_mb": round(total_db / (1024 * 1024), 2),
        "wal_size_mb": round(total_wal / (1024 * 1024), 2),
        "wal_ratio": round(wal_ratio, 4),
    }
