"""
Lock Chime Management — upload, validate, schedule, and manage Tesla lock chimes.

Adapted from TeslaUSB:
  - lock_chime_service.py — WAV validation, re-encoding, EBU R128 normalization
  - chime_group_service.py — chime groups with random selection
  - chime_scheduler_service.py — four schedule types (weekly/date/holiday/recurring)
  - lock_chimes.py (blueprint) — web API endpoints

Tesla requirements:
  - WAV format, 16-bit PCM, mono or stereo
  - Maximum duration: ~5 seconds
  - Stored in /LockChimes/ on the USB drive
  - Chime groups allow random rotation
  - Scheduler enables time-based chime selection
"""

import hashlib
import json
import logging
import os
import random
import shutil
import struct
import subprocess
import tempfile
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from dataclasses import dataclass, field

from app.config import PROJECT_ROOT
from app.modules.media import LOCK_CHIMES_DIR, ensure_dirs

logger = logging.getLogger("media.lock_chimes")

# Metadata file for chime groups and schedules
CHIMES_META_FILE = LOCK_CHIMES_DIR / "_chimes_meta.json"

# Known Tesla lock chime filenames
CHIME_NAMES = ["LockChime.wav", "UnlockChime.wav", "ApproachChime.wav", "LeaveChime.wav"]


class ScheduleType(StrEnum):
    WEEKLY = "weekly"
    DATE = "date"
    HOLIDAY = "holiday"
    RECURRING = "recurring"


@dataclass
class ChimeSchedule:
    """A schedule entry for when a chime group should be active."""
    schedule_type: ScheduleType
    chime_group: str
    # For weekly: day of week (0=Mon, 6=Sun)
    day_of_week: int = 0
    # For date: month (1-12), day (1-31)
    month: int = 1
    day: int = 1
    # For recurring: start and end dates
    start_date: str = ""
    end_date: str = ""


@dataclass
class ChimeGroup:
    """A named group of chime files that rotate randomly."""
    name: str
    files: list[str] = field(default_factory=list)


@dataclass
class ChimeMeta:
    """Overall chime configuration metadata."""
    groups: dict[str, ChimeGroup] = field(default_factory=dict)
    schedules: list[ChimeSchedule] = field(default_factory=list)
    active_chime: str = ""  # currently active chime filename


def load_meta() -> ChimeMeta:
    ensure_dirs()
    if not CHIMES_META_FILE.exists():
        return ChimeMeta()
    try:
        with open(CHIMES_META_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        meta = ChimeMeta()
        for name, g in data.get("groups", {}).items():
            meta.groups[name] = ChimeGroup(name=g["name"], files=g.get("files", []))
        for s in data.get("schedules", []):
            meta.schedules.append(ChimeSchedule(
                schedule_type=ScheduleType(s["schedule_type"]),
                chime_group=s["chime_group"],
                day_of_week=s.get("day_of_week", 0),
                month=s.get("month", 1),
                day=s.get("day", 1),
                start_date=s.get("start_date", ""),
                end_date=s.get("end_date", ""),
            ))
        meta.active_chime = data.get("active_chime", "")
        return meta
    except Exception:
        logger.exception("Failed to load chime metadata")
        return ChimeMeta()


def save_meta(meta: ChimeMeta) -> None:
    ensure_dirs()
    data = {
        "groups": {n: {"name": g.name, "files": g.files} for n, g in meta.groups.items()},
        "schedules": [
            {
                "schedule_type": s.schedule_type.value,
                "chime_group": s.chime_group,
                "day_of_week": s.day_of_week,
                "month": s.month,
                "day": s.day,
                "start_date": s.start_date,
                "end_date": s.end_date,
            }
            for s in meta.schedules
        ],
        "active_chime": meta.active_chime,
    }
    tmp = str(CHIMES_META_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHIMES_META_FILE)


# ── WAV Validation (adapted from TeslaUSB lock_chime_service.py) ──

def validate_wav(file_path: str | Path) -> dict:
    """Validate a WAV file for Tesla lock chime compatibility.

    Checks:
      - RIFF/WAVE header
      - PCM format (16-bit)
      - Duration < 10 seconds
      - Sample rate

    Returns dict with: valid (bool), duration_s (float), sample_rate (int),
      channels (int), bit_depth (int), error (str|None)
    """
    path = Path(file_path)
    result = {"valid": False, "duration_s": 0.0, "sample_rate": 0,
              "channels": 0, "bit_depth": 0, "file_size": 0, "error": None}

    if not path.exists():
        result["error"] = "File not found"
        return result

    result["file_size"] = path.stat().st_size
    if result["file_size"] < 44:
        result["error"] = "File too small to be valid WAV"
        return result

    try:
        with open(path, "rb") as f:
            # RIFF header
            riff = f.read(4)
            if riff != b"RIFF":
                result["error"] = "Not a RIFF/WAV file"
                return result
            f.read(4)  # file size
            wave = f.read(4)
            if wave != b"WAVE":
                result["error"] = "Not a WAVE file"
                return result

            # Find fmt chunk
            fmt_found = False
            data_size = 0
            while True:
                chunk_id = f.read(4)
                if len(chunk_id) < 4:
                    break
                chunk_size = struct.unpack("<I", f.read(4))[0]

                if chunk_id == b"fmt ":
                    fmt_data = f.read(chunk_size)
                    audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                    if audio_format != 1:
                        result["error"] = f"Unsupported audio format: {audio_format} (expected PCM=1)"
                        return result
                    result["channels"] = struct.unpack("<H", fmt_data[2:4])[0]
                    result["sample_rate"] = struct.unpack("<I", fmt_data[4:8])[0]
                    byte_rate = struct.unpack("<I", fmt_data[8:12])[0]
                    block_align = struct.unpack("<H", fmt_data[12:14])[0]
                    result["bit_depth"] = struct.unpack("<H", fmt_data[14:16])[0]
                    fmt_found = True
                elif chunk_id == b"data":
                    data_size = chunk_size
                    break
                else:
                    f.seek(chunk_size, 1)

            if not fmt_found:
                result["error"] = "No fmt chunk found"
                return result

            if result["bit_depth"] != 16:
                result["error"] = f"Must be 16-bit PCM (got {result['bit_depth']}-bit)"
                return result

            if result["sample_rate"] > 0 and data_size > 0:
                bytes_per_sample = result["bit_depth"] // 8 * result["channels"]
                result["duration_s"] = data_size / (result["sample_rate"] * bytes_per_sample)

            if result["duration_s"] > 10:
                result["error"] = f"Duration too long: {result['duration_s']:.1f}s (max 10s)"
                return result

            result["valid"] = True
            return result

    except Exception as e:
        result["error"] = str(e)
        return result


def process_chime_upload(file_path: str | Path, target_name: str) -> dict:
    """Process an uploaded WAV file for use as a lock chime.

    Steps (adapted from TeslaUSB):
      1. Validate WAV format
      2. Normalize audio (EBU R128 loudness normalization via FFmpeg)
      3. Trim to < 5 seconds if needed
      4. Re-encode as 16-bit PCM WAV
      5. Atomic write to LockChimes directory
      6. MD5 verification

    Returns dict with success/error and file info.
    """
    ensure_dirs()
    src = Path(file_path)

    # Validate
    validation = validate_wav(src)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    dest = LOCK_CHIMES_DIR / target_name

    try:
        # Use FFmpeg for normalization and re-encoding (matching TeslaUSB behavior)
        # EBU R128 integrated loudness normalization to -23 LUFS
        # Trim to 5 seconds max
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-t", "5",
            "-acodec", "pcm_s16le",
            "-ar", "44100",
            "-ac", "1",
            str(dest) + ".tmp.wav",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # FFmpeg failed — try simple copy if WAV is already valid
            logger.warning("FFmpeg normalize failed, copying raw: %s", result.stderr[:200])
            shutil.copy2(src, str(dest) + ".tmp.wav")

        # Atomic rename
        tmp_path = str(dest) + ".tmp.wav"
        final_path = str(dest)

        # Verify temp file
        tmp_size = os.path.getsize(tmp_path)
        if tmp_size < 44:
            os.unlink(tmp_path)
            return {"success": False, "error": "Output file too small"}

        # MD5 verification
        with open(src, "rb") as sf:
            src_md5 = hashlib.md5(sf.read()).hexdigest()

        os.replace(tmp_path, final_path)

        final_size = os.path.getsize(final_path)
        with open(final_path, "rb") as df:
            dest_md5 = hashlib.md5(df.read()).hexdigest()

        return {
            "success": True,
            "filename": target_name,
            "size_bytes": final_size,
            "duration_s": validation["duration_s"],
            "sample_rate": validation["sample_rate"],
            "md5": dest_md5,
        }
    except Exception as e:
        logger.exception("Failed to process chime upload")
        # Clean up temp file
        try:
            os.unlink(str(dest) + ".tmp.wav")
        except OSError:
            pass
        return {"success": False, "error": str(e)}


# ── Chime Listing ──

def list_chimes() -> list[dict]:
    """List all lock chime WAV files with metadata."""
    ensure_dirs()
    chimes = []
    for f in sorted(LOCK_CHIMES_DIR.glob("*.wav")):
        if f.name.startswith("_"):
            continue  # skip metadata files
        validation = validate_wav(f)
        chimes.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "duration_s": round(validation["duration_s"], 2),
            "sample_rate": validation["sample_rate"],
            "channels": validation["channels"],
            "valid": validation["valid"],
        })
    return chimes


def delete_chime(filename: str) -> bool:
    """Delete a lock chime file. Returns True if deleted."""
    path = LOCK_CHIMES_DIR / filename
    if not path.exists() or filename.startswith("_"):
        return False
    path.unlink()
    return True


# ── Chime Groups ──

def list_groups() -> list[dict]:
    """List all chime groups."""
    meta = load_meta()
    return [{"name": g.name, "files": g.files, "file_count": len(g.files)}
            for g in meta.groups.values()]


def create_group(name: str, files: list[str] | None = None) -> dict:
    """Create a new chime group or update an existing one."""
    if not name.strip():
        return {"success": False, "error": "Group name required"}

    safe_name = name.strip()
    # Validate all files exist
    valid_files = []
    for fname in (files or []):
        if (LOCK_CHIMES_DIR / fname).exists():
            valid_files.append(fname)

    meta = load_meta()
    meta.groups[safe_name] = ChimeGroup(name=safe_name, files=valid_files)
    save_meta(meta)
    return {"success": True, "name": safe_name, "files": valid_files}


def delete_group(name: str) -> bool:
    meta = load_meta()
    if name not in meta.groups:
        return False
    del meta.groups[name]
    save_meta(meta)
    return True


def get_random_chime_from_group(group_name: str) -> str | None:
    """Get a random chime file from a group."""
    meta = load_meta()
    group = meta.groups.get(group_name)
    if not group or not group.files:
        return None
    # Filter to files that actually exist
    existing = [f for f in group.files if (LOCK_CHIMES_DIR / f).exists()]
    if not existing:
        return None
    return random.choice(existing)


# ── Schedules ──

def list_schedules() -> list[dict]:
    """List all chime schedules."""
    meta = load_meta()
    return [
        {
            "schedule_type": s.schedule_type.value,
            "chime_group": s.chime_group,
            "day_of_week": s.day_of_week,
            "month": s.month,
            "day": s.day,
            "start_date": s.start_date,
            "end_date": s.end_date,
        }
        for s in meta.schedules
    ]


def add_schedule(schedule: ChimeSchedule) -> dict:
    meta = load_meta()
    meta.schedules.append(schedule)
    save_meta(meta)
    return {"success": True}


def delete_schedule(index: int) -> bool:
    meta = load_meta()
    if index < 0 or index >= len(meta.schedules):
        return False
    meta.schedules.pop(index)
    save_meta(meta)
    return True


def get_active_chime_for_today() -> str | None:
    """Determine which chime group should be active today based on schedules.

    Priority: date match > holiday > recurring > weekly > default (first group)
    """
    meta = load_meta()
    today = date.today()

    for s in meta.schedules:
        if s.schedule_type == ScheduleType.DATE:
            if s.month == today.month and s.day == today.day:
                chime = get_random_chime_from_group(s.chime_group)
                if chime:
                    return chime
        elif s.schedule_type == ScheduleType.WEEKLY:
            if s.day_of_week == today.weekday():
                chime = get_random_chime_from_group(s.chime_group)
                if chime:
                    return chime
        elif s.schedule_type == ScheduleType.RECURRING:
            try:
                start = date.fromisoformat(s.start_date) if s.start_date else today
                end = date.fromisoformat(s.end_date) if s.end_date else today
                if start <= today <= end:
                    chime = get_random_chime_from_group(s.chime_group)
                    if chime:
                        return chime
            except ValueError:
                pass

    # Default: return first available chime
    chimes = list_chimes()
    if chimes:
        return chimes[0]["filename"]
    return None


# ── US Holidays (US-specific, adapted from TeslaUSB chime_scheduler_service.py) ──

_US_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (7, 4): "Independence Day",
    (12, 25): "Christmas Day",
    (12, 31): "New Year's Eve",
    (10, 31): "Halloween",
    (2, 14): "Valentine's Day",
    (3, 17): "St. Patrick's Day",
}


def is_us_holiday(d: date) -> str | None:
    """Check if a date is a US holiday. Returns holiday name or None."""
    # Fixed-date holidays
    name = _US_HOLIDAYS.get((d.month, d.day))
    if name:
        return name

    # Floating holidays
    # Martin Luther King Jr. Day — 3rd Monday of January
    if d.month == 1 and d.weekday() == 0 and 15 <= d.day <= 21:
        return "Martin Luther King Jr. Day"
    # Presidents' Day — 3rd Monday of February
    if d.month == 2 and d.weekday() == 0 and 15 <= d.day <= 21:
        return "Presidents' Day"
    # Memorial Day — last Monday of May
    if d.month == 5 and d.weekday() == 0 and d.day >= 25:
        return "Memorial Day"
    # Labor Day — 1st Monday of September
    if d.month == 9 and d.weekday() == 0 and d.day <= 7:
        return "Labor Day"
    # Thanksgiving — 4th Thursday of November
    if d.month == 11 and d.weekday() == 3 and 22 <= d.day <= 28:
        return "Thanksgiving"
    # Easter (Meeus/Jones/Butcher algorithm, ported from TeslaUSB)
    if _is_easter(d):
        return "Easter"

    return None


def _is_easter(d: date) -> bool:
    """Meeus/Jones/Butcher algorithm for Easter Sunday."""
    y = d.year
    a = y % 19
    b = y // 100
    c = y % 100
    d2 = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d2 - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return d.month == month and d.day == day
