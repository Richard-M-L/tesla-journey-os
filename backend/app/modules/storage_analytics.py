"""
Storage Analytics — disk usage, video statistics, folder breakdown.

Adapted from TeslaUSB's analytics_service.py.
"""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from app.config import PROJECT_ROOT, config

logger = logging.getLogger("storage_analytics")


def get_disk_usage() -> dict:
    """Get disk usage for the project data volume."""
    data_dir = Path(PROJECT_ROOT) / "data"
    try:
        usage = shutil.disk_usage(str(data_dir))
        return {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "used_pct": round((usage.used / usage.total) * 100, 1),
        }
    except OSError:
        return {"total_gb": 0, "used_gb": 0, "free_gb": 0, "used_pct": 0}


def get_video_stats() -> dict:
    """Get video count and size by folder/directory."""
    folders: dict[str, dict] = {}

    for search_dir in [config.ingestion.watch_dir, config.ingestion.archive_dir,
                       config.ingestion.import_dir]:
        p = Path(search_dir)
        if not p.exists():
            continue

        folder_name = p.name
        count = 0
        total_size = 0
        oldest: str | None = None
        newest: str | None = None

        for mp4 in p.glob("**/*.mp4"):
            try:
                st = mp4.stat()
                count += 1
                total_size += st.st_size
                mtime = datetime.fromtimestamp(st.st_mtime)
                if oldest is None or mtime < datetime.fromisoformat(oldest):
                    oldest = mtime.isoformat()
                if newest is None or mtime > datetime.fromisoformat(newest):
                    newest = mtime.isoformat()
            except OSError:
                continue

        folders[folder_name] = {
            "path": str(p),
            "video_count": count,
            "total_size_bytes": total_size,
            "total_size_gb": round(total_size / (1024**3), 2),
            "oldest": oldest,
            "newest": newest,
        }

    total_videos = sum(f["video_count"] for f in folders.values())
    total_size = sum(f["total_size_bytes"] for f in folders.values())

    return {
        "folders": folders,
        "total_videos": total_videos,
        "total_size_gb": round(total_size / (1024**3), 2),
    }


def estimate_recording_time() -> dict:
    """Estimate remaining recording time based on free space.

    Tesla dashcam writes ~1.8 GB/hour at highest quality (4 cameras, H.264).
    """
    disk = get_disk_usage()
    free_gb = disk["free_gb"]

    # Average TeslaCam bitrate: ~4 Mbps total for 4 cameras = ~1.8 GB/hour
    gb_per_hour = 1.8
    hours = free_gb / gb_per_hour

    return {
        "free_gb": free_gb,
        "estimated_hours": round(hours, 1),
        "estimated_minutes": round(hours * 60),
        "gb_per_hour": gb_per_hour,
    }


def get_storage_health() -> dict:
    """Overall storage health summary."""
    disk = get_disk_usage()
    videos = get_video_stats()
    recording = estimate_recording_time()

    severity = "ok"
    if disk["used_pct"] > 95:
        severity = "error"
    elif disk["used_pct"] > 80:
        severity = "warn"

    alerts = []
    if disk["used_pct"] > 95:
        alerts.append({"severity": "error",
                       "message": f"Disk {disk['used_pct']}% full — {disk['free_gb']} GB remaining"})
    elif disk["used_pct"] > 80:
        alerts.append({"severity": "warn",
                       "message": f"Disk {disk['used_pct']}% full — consider cleanup"})

    if videos["total_videos"] == 0:
        alerts.append({"severity": "info", "message": "No dashcam videos found"})

    # Check DB size
    db_path = Path(PROJECT_ROOT) / "data" / "tjos.db"
    if db_path.exists():
        db_size_mb = db_path.stat().st_size / (1024**2)
        if db_size_mb > 500:
            alerts.append({"severity": "warn",
                           "message": f"Database is {db_size_mb:.0f} MB — consider archiving old data"})

    return {
        "severity": severity,
        "disk": disk,
        "video_stats": videos,
        "recording_estimate": recording,
        "alerts": alerts,
    }


def get_folder_breakdown() -> list[dict]:
    """Get size breakdown sorted largest first."""
    videos = get_video_stats()
    folders = []
    for name, info in videos["folders"].items():
        folders.append({
            "name": name,
            "video_count": info["video_count"],
            "size_gb": info["total_size_gb"],
            "pct": round((info["total_size_bytes"] / max(sum(f["total_size_bytes"]
                          for f in videos["folders"].values()), 1)) * 100, 1),
        })
    return sorted(folders, key=lambda f: f["size_gb"], reverse=True)
