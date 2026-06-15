"""
Video Service — browse, stream, and serve TeslaCam videos with telemetry.

Provides:
  - Video listing with metadata
  - HTTP Range-based streaming (byte-range for seeking)
  - Per-video telemetry data for HUD overlay
  - Video file discovery across TeslaCam and Archived directories
"""

import logging
import os
from pathlib import Path
from datetime import datetime

from app.config import config

logger = logging.getLogger("video")

# Directories to search for videos
VIDEO_SOURCES = [
    config.ingestion.watch_dir,
    config.ingestion.archive_dir,
]


def list_videos(source: str | None = None, limit: int = 100) -> list[dict]:
    """List available MP4 videos with metadata.

    Args:
        source: Filter by source dir name ("teslacam" or "archived"). None = both.
        limit: Max results.
    """
    videos = []
    search_dirs = VIDEO_SOURCES if source is None else [
        d for d in VIDEO_SOURCES if Path(source).name in d
    ]

    for search_dir in search_dirs:
        p = Path(search_dir)
        if not p.exists():
            continue
        for mp4 in sorted(p.glob("**/*.mp4"), key=lambda f: f.stat().st_mtime, reverse=True):
            try:
                st = mp4.stat()
                videos.append({
                    "path": str(mp4.absolute()),
                    "filename": mp4.name,
                    "folder": mp4.parent.name,
                    "source": "teslacam" if "teslacam" in str(mp4).lower() or "TeslaCam" in str(mp4) else "archived",
                    "size_bytes": st.st_size,
                    "size_mb": round(st.st_size / (1024 * 1024), 1),
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                    "has_sidecar": (mp4.with_suffix(".sei.json")).exists(),
                })
            except OSError:
                continue
            if len(videos) >= limit:
                break
        if len(videos) >= limit:
            break

    return videos


def get_video_info(video_path: str) -> dict | None:
    """Get detailed info for a single video, including telemetry frame count."""
    p = Path(video_path)
    if not p.exists():
        return None

    st = p.stat()
    info = {
        "path": str(p.absolute()),
        "filename": p.name,
        "size_bytes": st.st_size,
        "size_mb": round(st.st_size / (1024 * 1024), 1),
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "has_sidecar": (p.with_suffix(".sei.json")).exists(),
        "has_gps": False,
        "frame_count": 0,
        "duration_s": 0.0,
    }

    # Quick peek at telemetry via sidecar or parser
    try:
        from app.modules.ingestion.parser import SeiParser
        parser = SeiParser(str(p))
        frames = list(parser.parse())
        if frames:
            info["frame_count"] = len(frames)
            info["duration_s"] = round(frames[-1].timestamp_ms / 1000, 1) if frames[-1].timestamp_ms else 0
            info["has_gps"] = any(f.has_gps for f in frames)
            info["gps_frame_count"] = sum(1 for f in frames if f.has_gps)
    except Exception:
        pass

    return info


def get_video_telemetry(video_path: str, sample_rate: int = 10) -> list[dict]:
    """Get decimated telemetry for HUD overlay during video playback.

    Returns lightweight records with timestamp_ms, speed, gear, AP state,
    brake, blinkers, steering — everything needed for a real-time overlay.
    """
    p = Path(video_path)
    if not p.exists():
        return []

    try:
        from app.modules.ingestion.parser import SeiParser
        parser = SeiParser(str(p), sample_rate=sample_rate)
        frames = list(parser.parse())

        return [
            {
                "frame_index": f.frame_index,
                "timestamp_ms": round(f.timestamp_ms, 1),
                "speed_mps": round(f.speed_mps, 2),
                "speed_kmh": round(f.speed_kmh, 1),
                "gear": f.gear,
                "is_autopilot_on": f.is_autopilot_on,
                "autopilot_state": f.autopilot_state,
                "brake_applied": f.brake_applied,
                "blinker_left": f.blinker_left,
                "blinker_right": f.blinker_right,
                "steering_angle": round(f.steering_angle_deg, 1) if f.steering_angle_deg else None,
                "acceleration_x": round(f.acceleration_x, 2) if f.acceleration_x is not None else None,
                "has_gps": f.has_gps,
                "latitude": f.latitude,
                "longitude": f.longitude,
                "heading": f.heading,
            }
            for f in frames
        ]
    except Exception:
        logger.exception("Failed to get telemetry for %s", video_path)
        return []


def stream_video(video_path: str, start: int = 0, end: int | None = None) -> tuple[bytes, int, int, str]:
    """Read a byte range from a video file for HTTP Range streaming.

    Returns: (data, file_size, content_length, content_range_header_value)
    """
    p = Path(video_path)
    if not p.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    file_size = p.stat().st_size

    if end is None or end >= file_size:
        end = file_size - 1

    content_length = end - start + 1

    with open(p, "rb") as f:
        f.seek(start)
        data = f.read(content_length)

    content_range = f"bytes {start}-{end}/{file_size}"
    return data, file_size, content_length, content_range


def delete_video(video_path: str) -> bool:
    """Delete a video file and its sidecar."""
    p = Path(video_path)
    deleted = False
    if p.exists():
        p.unlink()
        deleted = True
    sidecar = p.with_suffix(".sei.json")
    if sidecar.exists():
        sidecar.unlink()
    return deleted
