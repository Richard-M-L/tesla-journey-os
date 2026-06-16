"""
Tesla Journey OS — REST API Routes.

All API endpoints for the React frontend.
Every endpoint works without GPS — endpoints that return coordinates
include a `has_gps` flag for graceful degradation.
"""

import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.modules import query, analytics, geo

router = APIRouter(prefix="/api")


# ── Stats ──────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    """System-wide statistics overview."""
    return query.get_stats_overview(db)


@router.get("/stats/dashboard")
def get_dashboard_stats(db: Session = Depends(get_db)):
    """Dashboard-ready statistics."""
    return {
        "overview": query.get_stats_overview(db),
        "trip_summary": analytics.get_trip_summary(db, days=30),
        "event_distribution": analytics.get_event_distribution(db, days=30),
        "driving_score": analytics.get_driving_score(db, days=30),
    }


# ── Trips ──────────────────────────────────────────

@router.get("/trips")
def list_trips(
    days: int | None = Query(None, description="Filter to last N days"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List trips, most recent first."""
    return {
        "trips": query.list_trips(db, days=days, limit=limit, offset=offset),
    }


@router.get("/trips/{trip_id}")
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    """Get full trip detail with waypoints and events."""
    detail = query.get_trip_detail(db, trip_id)
    if not detail:
        return {"error": "Trip not found"}, 404
    return detail


@router.get("/trips/{trip_id}/telemetry")
def get_trip_telemetry(
    trip_id: int,
    sample_rate: int = Query(30, ge=1, le=300, description="Keep 1 out of every N frames"),
    db: Session = Depends(get_db),
):
    """Get telemetry data for a trip (decimated for chart rendering)."""
    telemetry = query.get_telemetry_for_trip(db, trip_id, sample_rate=sample_rate)
    return {
        "trip_id": trip_id,
        "sample_rate": sample_rate,
        "frame_count": len(telemetry),
        "telemetry": telemetry,
    }


@router.get("/trips/{trip_id}/speed-profile")
def get_trip_speed_profile(trip_id: int, db: Session = Depends(get_db)):
    """Get speed-over-time profile for a trip."""
    return {
        "trip_id": trip_id,
        "profile": analytics.get_speed_profile(db, trip_id),
    }


# ── Events ─────────────────────────────────────────

@router.get("/events")
def list_events(
    event_type: str | None = Query(None, description="Filter by event type"),
    severity: str | None = Query(None, description="Filter by severity"),
    trip_id: int | None = Query(None, description="Filter by trip"),
    days: int | None = Query(30, description="Filter to last N days"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List driving events with optional filters."""
    return {
        "events": query.list_events(db, event_type, severity, trip_id, days, limit, offset),
    }


# ── Analytics ──────────────────────────────────────

@router.get("/analytics/trips/daily")
def get_daily_trips(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get trip counts grouped by day."""
    return {
        "daily_trips": query.get_trips_by_day(db, days),
    }


@router.get("/analytics/battery")
def get_battery_trend(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get battery level trend over time."""
    return {
        "battery_trend": analytics.get_battery_trend(db, days),
    }


@router.get("/analytics/score")
def get_driving_score(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """Get driving behavior score."""
    return analytics.get_driving_score(db, days)


# ── Geo (optional) ─────────────────────────────────

@router.get("/geo/reverse")
async def reverse_geocode(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    provider: str = Query("cache", description="cache | nominatim | amap"),
    db: Session = Depends(get_db),
):
    """Reverse geocode a coordinate.

    When provider='cache', returns cached data only (no external API call).
    Use 'nominatim' or 'amap' to resolve on-demand.
    """
    if provider == "cache":
        result = await geo.resolve(db, lat, lon)
    else:
        result = await geo.resolve_with_provider(db, lat, lon, provider)

    return {
        "latitude": lat,
        "longitude": lon,
        **result,
    }


# ── USB Gadget ─────────────────────────────────────

@router.get("/usb/status")
def get_usb_status():
    """Get USB gadget status (present/edit/unknown, LUN info)."""
    try:
        from app.modules.usb import usb_manager
        return usb_manager.get_status()
    except ImportError:
        return {"supported": False, "mode": "unsupported", "active": False,
                "error": "USB gadget module not available (Linux only)"}


@router.post("/usb/mode/{mode}")
async def set_usb_mode(mode: str):
    """Switch USB gadget mode: present or edit."""
    if mode not in ("present", "edit"):
        return {"success": False, "error": "Mode must be 'present' or 'edit'"}, 400

    try:
        from app.modules.usb import usb_manager
        if mode == "present":
            ok = usb_manager.present()
        else:
            ok = usb_manager.edit()
        return {"success": ok, "mode": mode}
    except ImportError:
        return {"success": False, "error": "USB gadget not available"}


@router.post("/usb/setup")
async def setup_usb_gadget():
    """Create the USB gadget configuration (requires root)."""
    try:
        from app.modules.usb import usb_manager
        ok = usb_manager.setup()
        return {"success": ok}
    except ImportError:
        return {"success": False, "error": "USB gadget not available"}


# ── Media: Lock Chimes ─────────────────────────────

@router.get("/media/chimes")
def list_lock_chimes():
    from app.modules.media.lock_chimes import list_chimes, list_groups, list_schedules
    return {
        "chimes": list_chimes(),
        "groups": list_groups(),
        "schedules": list_schedules(),
    }


@router.post("/media/chimes/upload")
async def upload_chime_file(file: UploadFile):
    from app.modules.media.lock_chimes import process_chime_upload
    suffix = os.path.splitext(file.filename or "chime.wav")[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        result = process_chime_upload(tmp_path, file.filename or "LockChime.wav")
        return result
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.delete("/media/chimes/{filename}")
def delete_lock_chime(filename: str):
    from app.modules.media.lock_chimes import delete_chime
    return {"success": delete_chime(filename)}


@router.post("/media/chimes/groups")
def create_chime_group(name: str, files: list[str] | None = None):
    from app.modules.media.lock_chimes import create_group
    return create_group(name, files or [])


@router.delete("/media/chimes/groups/{name}")
def delete_chime_group(name: str):
    from app.modules.media.lock_chimes import delete_group
    return {"success": delete_group(name)}


@router.post("/media/chimes/schedules")
def add_chime_schedule(
    schedule_type: str,
    chime_group: str,
    day_of_week: int = 0,
    month: int = 1,
    day: int = 1,
    start_date: str = "",
    end_date: str = "",
):
    from app.modules.media.lock_chimes import ChimeSchedule, ScheduleType, add_schedule
    return add_schedule(ChimeSchedule(
        schedule_type=ScheduleType(schedule_type),
        chime_group=chime_group,
        day_of_week=day_of_week,
        month=month,
        day=day,
        start_date=start_date,
        end_date=end_date,
    ))


# ── Media: Light Shows ─────────────────────────────

@router.get("/media/lightshows")
def list_light_shows():
    from app.modules.media.light_shows import list_shows
    return {"shows": list_shows()}


@router.post("/media/lightshows/upload")
async def upload_light_show(file: UploadFile):
    import tempfile, os
    from app.modules.media.light_shows import upload_zip, upload_single
    suffix = os.path.splitext(file.filename or "show.zip")[1] or ".zip"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        if suffix.lower() == ".zip":
            return upload_zip(tmp_path)
        else:
            return upload_single(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.delete("/media/lightshows/{name}")
def delete_light_show(name: str):
    from app.modules.media.light_shows import delete_show
    count = delete_show(name)
    return {"success": count > 0, "deleted": count}


# ── Media: Music ────────────────────────────────────

@router.get("/media/music")
def list_music():
    import os
    from pathlib import Path
    from app.modules.media import MUSIC_DIR, ensure_dirs
    ensure_dirs()
    files = []
    for f in sorted(MUSIC_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in (".mp3", ".flac", ".wav", ".aac", ".m4a"):
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "ext": f.suffix.lower(),
            })
    return {"files": files, "count": len(files)}


@router.post("/media/music/upload")
async def upload_music(file: UploadFile):
    import tempfile, os, shutil
    from app.modules.media import MUSIC_DIR, ensure_dirs
    ensure_dirs()
    suffix = os.path.splitext(file.filename or "track.mp3")[1] or ".mp3"
    dest = MUSIC_DIR / (file.filename or "track.mp3")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        tmp_dest = str(dest) + ".tmp"
        shutil.copy2(tmp_path, tmp_dest)
        os.replace(tmp_dest, str(dest))
        return {"success": True, "filename": file.filename, "size_bytes": dest.stat().st_size}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.delete("/media/music/{filename}")
def delete_music(filename: str):
    from app.modules.media import MUSIC_DIR
    path = MUSIC_DIR / filename
    if path.exists():
        path.unlink()
        return {"success": True}
    return {"success": False, "error": "File not found"}


# ── WiFi ────────────────────────────────────────────

@router.get("/wifi/status")
def get_wifi_status():
    from app.modules.wifi import get_status
    return get_status()


@router.get("/wifi/scan")
def scan_wifi():
    from app.modules.wifi import scan_networks
    return {"networks": scan_networks()}


@router.get("/wifi/saved")
def get_saved_wifi():
    from app.modules.wifi import get_saved_networks
    return {"saved": get_saved_networks()}


@router.post("/wifi/connect")
def connect_wifi(ssid: str, password: str = ""):
    from app.modules.wifi import connect_to_ssid
    return connect_to_ssid(ssid, password)


@router.delete("/wifi/forget/{name}")
def forget_wifi(name: str):
    from app.modules.wifi import forget_network
    return forget_network(name)


@router.post("/wifi/reorder")
async def reorder_wifi(request: Request):
    """Reorder saved WiFi network priorities. Body: {"names": ["net1","net2",...]}"""
    from app.modules.wifi import _nmcli
    try:
        body = await request.json()
        names = body.get("names", [])
    except Exception:
        return {"success": False, "error": "无效的 JSON"}
    for i, name in enumerate(names):
        pri = 100 - (i * 10)
        _nmcli(["connection", "modify", name, "connection.autoconnect-priority", str(pri)])
    return {"success": True, "reordered": len(names)}


# ── AP / Hotspot ─────────────────────────────────────

@router.get("/ap/status")
def get_ap_status():
    from app.modules.ap import ap_status
    return ap_status()


@router.get("/ap/config")
def get_ap_config_route():
    from app.modules.ap import get_ap_config
    return get_ap_config()


@router.post("/ap/config")
def update_ap_config_route(ssid: str, passphrase: str = ""):
    from app.modules.ap import update_ap_config
    return update_ap_config(ssid, passphrase)


@router.post("/ap/force-mode")
def set_ap_force_mode(mode: str):
    from app.modules.ap import set_force_mode
    return set_force_mode(mode)


# ── Settings ─────────────────────────────────────────

@router.get("/settings/config")
def get_full_config():
    """Return non-sensitive parts of the config for the settings UI."""
    return {
        "ap": {
            "ssid": config.ap.ssid,
            "channel": config.ap.channel,
            "enabled": config.ap.enabled,
            "force_mode": config.ap.force_mode,
        },
        "web": {"port": config.web.port},
        "ingestion": {"sample_rate": config.ingestion.sample_rate},
        "trip": {
            "gap_minutes": config.trip.gap_minutes,
            "min_duration_seconds": config.trip.min_duration_seconds,
            "min_distance_km": config.trip.min_distance_km,
        },
        "events": {
            "emergency_brake": {"enabled": config.events.emergency_brake.enabled, "threshold_ms2": config.events.emergency_brake.threshold_ms2},
            "harsh_brake": {"enabled": config.events.harsh_brake.enabled, "threshold_ms2": config.events.harsh_brake.threshold_ms2},
            "hard_acceleration": {"enabled": config.events.hard_acceleration.enabled, "threshold_ms2": config.events.hard_acceleration.threshold_ms2},
        },
    }


@router.post("/settings/config")
async def save_settings(request: Request):
    """Atomically update config.yaml with settings changes."""
    import yaml, os
    from app.config import CONFIG_PATH

    try:
        body = await request.json()
    except Exception:
        return {"success": False, "error": "Invalid JSON"}

    # Allowed keys and their YAML paths — whitelist for safety
    allowed_paths = {
        "ingestion.sample_rate": ("ingestion", "sample_rate", int),
        "trip.gap_minutes": ("trip", "gap_minutes", int),
        "trip.min_duration_seconds": ("trip", "min_duration_seconds", int),
        "trip.min_distance_km": ("trip", "min_distance_km", float),
        "events.emergency_brake.enabled": ("events", "emergency_brake", "enabled", bool),
        "events.emergency_brake.threshold_ms2": ("events", "emergency_brake", "threshold_ms2", float),
        "events.harsh_brake.enabled": ("events", "harsh_brake", "enabled", bool),
        "events.harsh_brake.threshold_ms2": ("events", "harsh_brake", "threshold_ms2", float),
        "events.hard_acceleration.enabled": ("events", "hard_acceleration", "enabled", bool),
        "events.hard_acceleration.threshold_ms2": ("events", "hard_acceleration", "threshold_ms2", float),
    }

    updated = []
    errors = []

    # Load current config
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    for key, value in body.items():
        if key not in allowed_paths:
            errors.append(f"Unknown key: {key}")
            continue

        path_parts = allowed_paths[key]
        try:
            cast = path_parts[-1]
            typed_value = cast(value)
        except (ValueError, TypeError):
            errors.append(f"Invalid value for {key}: {value}")
            continue

        # Navigate to the right spot in the YAML tree and set value
        if len(path_parts) == 3:  # section.key → value
            section, field, _ = path_parts
            raw.setdefault(section, {})[field] = typed_value
        elif len(path_parts) == 4:  # section.sub.key → value
            section, sub, field, _ = path_parts
            raw.setdefault(section, {}).setdefault(sub, {})[field] = typed_value

        updated.append(key)

    if not updated and errors:
        return {"success": False, "error": "; ".join(errors)}

    # Atomic write
    tmp_path = str(CONFIG_PATH) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, CONFIG_PATH)

    return {"success": True, "updated": updated, "errors": errors if errors else None}


# ── Ingestion Control ───────────────────────────────

@router.post("/ingestion/scan")
async def trigger_scan():
    """Manually trigger a full scan of the watch directory."""
    from app.modules.ingestion.watcher import FileWatcher
    watcher = FileWatcher()
    files = await watcher.scan_all()
    return {"success": True, "files_enqueued": len(files), "files": files[:20]}


# ── System Health ────────────────────────────────────

@router.get("/system/health")
def get_system_health():
    import shutil
    from app.config import PROJECT_ROOT
    from app.modules.watchdog import safe_mode, archive_watchdog, hardware_watchdog
    from app.modules.task_coordinator import coordinator

    # Disk usage
    disk = shutil.disk_usage(str(PROJECT_ROOT))
    disk_pct = (disk.used / disk.total) * 100

    # Database size
    db_path = PROJECT_ROOT / "data" / "tjos.db"
    db_size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
    wal_path = PROJECT_ROOT / "data" / "tjos.db-wal"
    wal_size_mb = wal_path.stat().st_size / (1024 * 1024) if wal_path.exists() else 0

    blocks = {
        "disk": {
            "severity": "error" if disk_pct > 95 else "warn" if disk_pct > 80 else "ok",
            "message": f"Disk {disk_pct:.0f}% used ({disk.free / (1024**3):.1f} GB free)",
            "used_pct": round(disk_pct, 1),
            "free_gb": round(disk.free / (1024**3), 1),
            "total_gb": round(disk.total / (1024**3), 1),
        },
        "database": {
            "severity": "ok",
            "message": f"DB {db_size_mb:.1f} MB, WAL {wal_size_mb:.1f} MB",
            "db_size_mb": round(db_size_mb, 1),
            "wal_size_mb": round(wal_size_mb, 1),
        },
        "watchdog": {
            "severity": "ok",
            "message": "Hardware watchdog active" if Path("/dev/watchdog").exists() else "Watchdog not available",
            "device_exists": Path("/dev/watchdog").exists(),
        },
        "safe_mode": {
            "severity": "error" if safe_mode.is_safe_mode() else "ok",
            "message": "SAFE MODE ACTIVE — heavy services disabled" if safe_mode.is_safe_mode() else "Normal operation",
            "active": safe_mode.is_safe_mode(),
            "recent_boots": len(safe_mode.get_reboot_history()),
        },
        "task_coordinator": {
            "severity": "ok",
            "message": f"Task: {coordinator.current_task or 'idle'}",
            **coordinator.get_status(),
        },
        "archive_watchdog": {
            "severity": "ok",
            "message": "Archive healthy",
            **archive_watchdog.check(queue_depth=0, worker_running=True),
        },
    }

    # Overall severity
    severities = {"ok": 0, "warn": 1, "error": 2}
    worst = "ok"
    for b in blocks.values():
        if severities.get(b.get("severity", "ok"), 0) > severities.get(worst, 0):
            worst = b["severity"]

    return {"overall": worst, "blocks": blocks}


@router.post("/system/safe-mode/disable")
def disable_safe_mode():
    from app.modules.watchdog import safe_mode
    safe_mode.disable()
    return {"success": True, "message": "Safe mode disabled. Restart to resume normal operation."}


@router.get("/system/reboot-history")
def get_reboot_history():
    from app.modules.watchdog import safe_mode
    boots = safe_mode.get_reboot_history()
    return {
        "count": len(boots),
        "timestamps": boots,
        "safe_mode_active": safe_mode.is_safe_mode(),
        "threshold": {"count": 3, "window_minutes": 10},
    }


# ── Video ───────────────────────────────────────────

@router.get("/videos")
def list_videos(source: str | None = None, limit: int = 100):
    from app.modules.video import list_videos as _list
    return {"videos": _list(source, limit)}


@router.get("/videos/info")
def get_video_info(path: str):
    from app.modules.video import get_video_info as _info
    info = _info(path)
    if info is None:
        return {"error": "Video not found"}, 404
    return info


@router.get("/videos/telemetry")
def get_video_telemetry(path: str, sample_rate: int = 10):
    from app.modules.video import get_video_telemetry as _telem
    return {"frames": _telem(path, sample_rate)}


@router.get("/videos/stream")
async def stream_video(path: str, request: Request = None):
    """HTTP Range streaming for video playback with seeking.

    Returns 206 Partial Content for range requests, 200 for full file.
    """
    from fastapi.responses import StreamingResponse
    from app.modules.video import stream_video as _stream

    try:
        # Parse Range header
        range_header = None
        if request and "range" in request.headers:
            range_header = request.headers["range"]

        p = Path(path)
        if not p.exists():
            return {"error": "Video not found"}, 404

        file_size = p.stat().st_size

        if range_header:
            # Parse "bytes=start-end"
            range_str = range_header.replace("bytes=", "")
            parts = range_str.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

            data, _, content_length, content_range = _stream(path, start, end)

            from fastapi.responses import Response
            return Response(
                content=data,
                status_code=206,
                headers={
                    "Content-Range": content_range,
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(content_length),
                    "Content-Type": "video/mp4",
                },
            )

        # Full file
        def file_iterator():
            with open(p, "rb") as f:
                while chunk := f.read(1024 * 1024):
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
        )

    except FileNotFoundError:
        return {"error": "Video not found"}, 404


@router.delete("/videos")
def delete_video(path: str):
    from app.modules.file_safety import safe_delete_video
    ok, reason = safe_delete_video(path)
    return {"success": ok, "reason": reason}


# ── Storage Analytics ────────────────────────────────

@router.get("/storage/health")
def get_storage_health():
    from app.modules.storage_analytics import get_storage_health as _health
    return _health()


@router.get("/storage/disk")
def get_disk_usage():
    from app.modules.storage_analytics import get_disk_usage as _disk
    return _disk()


@router.get("/storage/videos")
def get_video_stats():
    from app.modules.storage_analytics import get_video_stats as _vstats
    return _vstats()


@router.get("/storage/recording")
def estimate_recording():
    from app.modules.storage_analytics import estimate_recording_time as _est
    return _est()


@router.get("/storage/folders")
def get_folder_breakdown():
    from app.modules.storage_analytics import get_folder_breakdown as _breakdown
    return {"folders": _breakdown()}


# ── Wraps ────────────────────────────────────────────

@router.get("/media/wraps")
def list_wraps():
    from app.modules.media.wraps import list_wraps as _list
    return {"wraps": _list()}


@router.post("/media/wraps/upload")
async def upload_wrap(file: UploadFile):
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "wrap.png")[1] or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        from app.modules.media.wraps import upload_wrap as _upload
        return _upload(tmp_path, file.filename)
    finally:
        if tmp_path:
            try: os.unlink(tmp_path)
            except OSError: pass


@router.delete("/media/wraps/{filename}")
def delete_wrap(filename: str):
    from app.modules.media.wraps import delete_wrap as _del
    return {"success": _del(filename)}


# ── License Plates ───────────────────────────────────

@router.get("/media/plates")
def list_plates():
    from app.modules.media.wraps import list_plates as _list
    return {"plates": _list()}


@router.post("/media/plates/upload")
async def upload_plate(file: UploadFile):
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "plate.png")[1] or ".png"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        from app.modules.media.wraps import upload_plate as _upload
        return _upload(tmp_path, file.filename)
    finally:
        if tmp_path:
            try: os.unlink(tmp_path)
            except OSError: pass


@router.delete("/media/plates/{filename}")
def delete_plate(filename: str):
    from app.modules.media.wraps import delete_plate as _del
    return {"success": _del(filename)}


# ── Boombox ──────────────────────────────────────────

@router.get("/media/boombox")
def list_boombox():
    from app.modules.media.wraps import list_boombox as _list
    return {"sounds": _list()}


@router.post("/media/boombox/upload")
async def upload_boombox_sound(file: UploadFile):
    tmp_path = None
    try:
        suffix = os.path.splitext(file.filename or "sound.mp3")[1] or ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name
        from app.modules.media.wraps import upload_boombox as _upload
        return _upload(tmp_path)
    finally:
        if tmp_path:
            try: os.unlink(tmp_path)
            except OSError: pass


@router.delete("/media/boombox/{filename}")
def delete_boombox_sound(filename: str):
    from app.modules.media.wraps import delete_boombox as _del
    return {"success": _del(filename)}


# ── Media Export to USB ──────────────────────────────

@router.get("/media/export/preview")
def export_preview():
    from app.modules.media.export import get_export_preview
    return get_export_preview()


@router.get("/media/export/usb-drives")
def list_usb_drives():
    from app.modules.media.export import list_usb_drives
    return {"drives": list_usb_drives()}


@router.post("/media/export")
async def export_to_usb(request: Request):
    """Export all media files to a USB drive. Body: {target: "/path/to/usb", dry_run: false}"""
    try:
        body = await request.json()
    except Exception:
        return {"success": False, "error": "Invalid JSON"}

    target = body.get("target", "")
    dry_run = body.get("dry_run", False)

    if not target:
        return {"success": False, "error": "target path required"}

    from app.modules.media.export import export_to_usb as _export
    return _export(target, dry_run=dry_run)


# ── Updates ──────────────────────────────────────────

@router.get("/system/version")
def get_version():
    from app.modules.updater import get_current_version, get_current_commit
    return {
        "version": get_current_version(),
        "commit": get_current_commit(),
    }


@router.get("/system/updates/check")
def check_updates(force: bool = False):
    from app.modules.updater import check_for_updates
    return check_for_updates(force=force)


@router.post("/system/updates/apply")
async def apply_updates():
    """Start background update. Returns immediately."""
    from app.modules.updater import apply_updates as _apply
    return _apply()


@router.get("/system/updates/status")
def get_update_status():
    """Get current update progress."""
    from app.modules.updater import get_update_status as _status
    return _status()


# ── Pipeline Queue ───────────────────────────────────

@router.get("/system/queue/stats")
def get_queue_stats(db: Session = Depends(get_db)):
    from app.modules.pipeline_queue import get_queue_stats
    return get_queue_stats(db)


@router.get("/system/queue/dead-letters")
def list_dead_letters(db: Session = Depends(get_db)):
    from app.modules.pipeline_queue import get_dead_letters
    return {"items": get_dead_letters(db)}


@router.post("/system/queue/dead-letters/{item_id}/retry")
def retry_dead_letter(item_id: int, db: Session = Depends(get_db)):
    from app.modules.pipeline_queue import retry_dead_letter
    ok = retry_dead_letter(db, item_id)
    db.commit()
    return {"success": ok}


@router.delete("/system/queue/dead-letters/{item_id}")
def delete_dead_letter(item_id: int, db: Session = Depends(get_db)):
    from app.modules.pipeline_queue import delete_dead_letter
    ok = delete_dead_letter(db, item_id)
    db.commit()
    return {"success": ok}


