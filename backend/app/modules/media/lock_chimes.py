"""
Lock Chime Management — WAV validation, MP3 conversion, EBU R128 normalization,
chime groups, scheduling, and Chinese holiday support.

Adapted from TeslaUSB's lock_chime_service.py + chime_scheduler_service.py.

Features:
  - WAV validation (wave module: 16-bit PCM, 44.1/48kHz, mono/stereo, ≤1MB)
  - MP3→WAV auto-conversion via FFmpeg
  - EBU R128 two-pass loudness normalization (4 presets)
  - MD5-verified atomic file swap with directory fsync
  - Chime groups with random selection
  - Weekly / Date / Holiday / Recurring schedules
  - Chinese holidays: 春节, 清明节, 端午节, 中秋节, 国庆节, etc.
  - Startup random chime selection
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
import time
import wave
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from dataclasses import dataclass, field

from app.config import PROJECT_ROOT
from app.modules.media import LOCK_CHIMES_DIR, ensure_dirs

logger = logging.getLogger("media.lock_chimes")

# ── Constants ──
MAX_LOCK_CHIME_SIZE = 1_048_576       # 1 MB
MAX_LOCK_CHIME_DURATION = 10.0        # seconds
CHIMES_META_FILE = LOCK_CHIMES_DIR / "_chimes_meta.json"

# EBU R128 loudness presets
LOUDNESS_PRESETS = {
    "broadcast": {"lufs": -23, "label": "广播标准 (最安静)"},
    "streaming": {"lufs": -16, "label": "流媒体 (推荐)"},
    "loud":      {"lufs": -14, "label": "响亮 (Apple Music 级别)"},
    "maximum":   {"lufs": -12, "label": "最大 (安全上限)"},
}


# ── Data classes ──

class ScheduleType(StrEnum):
    WEEKLY = "weekly"
    DATE = "date"
    HOLIDAY = "holiday"
    RECURRING = "recurring"

@dataclass
class ChimeSchedule:
    id: int = 0
    name: str = ""
    chime_filename: str = ""       # "RANDOM" for random selection
    schedule_type: ScheduleType = ScheduleType.WEEKLY
    enabled: bool = True
    time: str = "00:00"            # HH:MM
    days: list[str] = field(default_factory=list)     # weekly: ["Mon","Tue"...]
    month: int = 1                 # date: 1-12
    day: int = 1                   # date: 1-31
    holiday: str = ""              # holiday name
    interval: str = ""             # recurring: "on_boot","15min","30min","1hour"...
    last_run: str = ""
    last_run_chime: str = ""

@dataclass
class ChimeGroup:
    id: str = ""
    name: str = ""
    description: str = ""
    files: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

@dataclass
class RandomConfig:
    enabled: bool = False
    group_id: str = ""
    last_selected: str = ""
    last_selected_at: str = ""


# ── WAV Validation ──

def validate_wav(file_path: str | Path) -> tuple[bool, str, dict]:
    """Validate WAV file for Tesla lock chime compatibility.

    Returns (is_valid, message, info_dict).
    """
    path = Path(file_path)
    info = {"size_bytes": 0, "duration_s": 0.0, "sample_rate": 0,
            "channels": 0, "bit_depth": 0}

    try:
        info["size_bytes"] = path.stat().st_size
    except OSError as e:
        return False, f"无法读取文件: {e}", info

    if info["size_bytes"] == 0:
        return False, "文件为空", info
    if info["size_bytes"] > MAX_LOCK_CHIME_SIZE:
        return False, f"文件 {info['size_bytes']/1e6:.1f} MB，特斯拉要求 ≤ 1 MB", info

    try:
        with wave.open(str(path), 'rb') as wf:
            info["channels"] = wf.getnchannels()
            info["sample_rate"] = wf.getframerate()
            info["bit_depth"] = wf.getsampwidth() * 8
            n_frames = wf.getnframes()
            if info["sample_rate"] > 0:
                info["duration_s"] = n_frames / info["sample_rate"]
    except (wave.Error, EOFError):
        return False, "不是有效的 WAV 文件", info
    except OSError as e:
        return False, f"无法读取文件: {e}", info

    if info["bit_depth"] != 16:
        return False, f"{info['bit_depth']}-bit，特斯拉要求 16-bit PCM", info
    if info["sample_rate"] not in (44100, 48000):
        return False, f"采样率 {info['sample_rate']/1000:.1f} kHz，特斯拉要求 44.1 或 48 kHz", info
    if info["channels"] not in (1, 2):
        return False, f"{info['channels']} 声道，特斯拉要求单声道或立体声", info

    return True, "有效", info


# ── FFmpeg Operations ──

def _run_ffmpeg(input_path: str, args: list[str], output_path: str, timeout: int = 30) -> tuple[bool, str]:
    """Run FFmpeg with timeout. Returns (success, error_string)."""
    cmd = ["ffmpeg", "-y", "-i", input_path] + args + [output_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            stderr = result.stderr or result.stdout or ""
            # Extract meaningful error
            for keyword in ["error", "invalid", "could not", "failed", "unable"]:
                for line in stderr.split("\n"):
                    if keyword in line.lower():
                        return False, line.strip()[:200]
            return False, stderr.strip()[-200:] or "FFmpeg 处理失败"
        return True, ""
    except FileNotFoundError:
        return False, "FFmpeg 未安装，请运行: sudo apt install ffmpeg"
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg 超时 ({timeout}s)"


def convert_mp3_to_wav(input_path: str) -> tuple[bool, str, str]:
    """Convert MP3 to WAV (PCM 16-bit, 44.1kHz, mono). Returns (success, error, output_path)."""
    tmp = tempfile.mktemp(suffix=".wav")
    ok, err = _run_ffmpeg(input_path,
        ["-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1"], tmp)
    return ok, err, tmp


def normalize_loudness(input_path: str, preset: str = "streaming") -> tuple[bool, str, str]:
    """Two-pass EBU R128 normalization. Returns (success, error, output_path)."""
    cfg = LOUDNESS_PRESETS.get(preset, LOUDNESS_PRESETS["streaming"])
    target = cfg["lufs"]

    # Pass 1: measure
    measure_args = ["-af", f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json",
                    "-f", "null", "-"]
    ok, err = _run_ffmpeg(input_path, measure_args, "/dev/null", timeout=30)
    if not ok:
        return False, f"测量失败: {err}", ""

    # Extract measured values from stderr
    measured = {}
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path] + measure_args,
            capture_output=True, text=True, timeout=30)
        stderr = result.stderr
        # Find JSON block
        brace_idx = stderr.rfind("{")
        if brace_idx >= 0:
            measured = json.loads(stderr[brace_idx:].split("\n}")[0] + "\n}")
    except (json.JSONDecodeError, ValueError):
        logger.debug("Could not parse loudnorm JSON, using defaults")

    # Pass 2: apply
    tmp = tempfile.mktemp(suffix=".wav")
    apply_args = ["-af", f"loudnorm=I={target}:TP=-1.5:LRA=11"
                  f":measured_I={measured.get('input_i', target)}"
                  f":measured_LRA={measured.get('input_lra', 11)}"
                  f":measured_TP={measured.get('input_tp', -1.5)}"
                  f":measured_thresh={measured.get('input_thresh', -33)}"
                  f":offset={measured.get('target_offset', 0)}",
                  "-ar", "44100"]
    ok, err = _run_ffmpeg(input_path, apply_args, tmp, timeout=30)
    if not ok:
        try: os.unlink(tmp)
        except OSError: pass
        return False, f"归一化失败: {err}", ""

    return True, "", tmp


def reencode_for_tesla(input_path: str) -> tuple[bool, str, str]:
    """Re-encode to Tesla-compatible WAV (PCM 16-bit, 44.1kHz, mono, trim to fit 1MB)."""
    tmp = tempfile.mktemp(suffix=".wav")
    # Calculate max duration to stay under 1 MB: (1MB - 200B header) / (44100 * 2 * 1) ≈ 11.88s
    max_sec = (MAX_LOCK_CHIME_SIZE - 200) / (44100 * 2 * 1)

    args = ["-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
            "-t", str(max_sec)]
    ok, err = _run_ffmpeg(input_path, args, tmp, timeout=30)
    if not ok:
        try: os.unlink(tmp)
        except OSError: pass
        return False, err, ""

    return True, "", tmp


# ── Atomic File Swap ──

def atomic_chime_swap(source_path: str, dest_name: str) -> tuple[bool, str]:
    """Atomically replace a lock chime file with MD5 verification."""
    ensure_dirs()
    dest = LOCK_CHIMES_DIR / dest_name

    # Compute source MD5
    src_md5 = _file_md5(source_path)

    # Backup existing
    backup = None
    if dest.exists():
        backup = LOCK_CHIMES_DIR / f"_{dest_name}.bak"
        shutil.copy2(dest, backup)

    try:
        # Atomic: write temp → fsync → rename → dir fsync
        tmp = dest.with_suffix(".tmp")
        shutil.copy2(source_path, tmp)

        # Verify temp size
        if tmp.stat().st_size != os.path.getsize(source_path):
            raise IOError("临时文件大小不匹配")

        # Fsync temp file
        with open(tmp, "r+b") as f:
            f.flush()
            os.fsync(f.fileno())

        # Atomic rename
        os.replace(str(tmp), str(dest))

        # Fsync directory
        fd = os.open(str(LOCK_CHIMES_DIR), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

        # Force mtime change
        os.utime(str(dest), None)

        # Sync
        subprocess.run(["sync"], timeout=10)

        # Verify destination MD5
        dest_md5 = _file_md5(str(dest))
        if dest_md5 != src_md5:
            raise IOError(f"MD5 不匹配: src={src_md5[:8]} dest={dest_md5[:8]}")

        # Cleanup
        if backup:
            try: backup.unlink()
            except OSError: pass

        return True, dest_name

    except Exception as e:
        # Restore backup
        if backup and backup.exists():
            try:
                shutil.copy2(backup, dest)
                backup.unlink()
            except OSError: pass
        try:
            tmp = dest.with_suffix(".tmp")
            if tmp.exists(): tmp.unlink()
        except OSError: pass
        return False, str(e)


def _file_md5(path: str) -> str:
    """Compute MD5 hash of a file in 64KB chunks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ── Upload Pipeline ──

def process_chime_upload(file_path: str, filename: str,
                         normalize: bool = True,
                         preset: str = "streaming") -> dict:
    """Full upload pipeline: validate → convert → normalize → atomic swap.

    Accepts WAV and MP3 files. MP3 is auto-converted to WAV.
    """
    ensure_dirs()
    src = file_path
    cleanup_paths = []

    try:
        # Step 1: Convert MP3→WAV if needed
        if filename.lower().endswith(".mp3"):
            ok, err, wav_path = convert_mp3_to_wav(src)
            if not ok:
                return {"success": False, "error": f"MP3 转换失败: {err}"}
            src = wav_path
            cleanup_paths.append(wav_path)
            filename = filename.rsplit(".", 1)[0] + ".wav"

        # Step 2: Validate
        valid, msg, info = validate_wav(src)
        if not valid:
            return {"success": False, "error": msg, "info": info}

        # Step 3: Re-encode to Tesla format
        ok, err, reencoded = reencode_for_tesla(src)
        if not ok:
            return {"success": False, "error": f"格式转换失败: {err}"}
        cleanup_paths.append(reencoded)
        src = reencoded

        # Step 4: Normalize (optional)
        if normalize:
            ok, err, normalized = normalize_loudness(src, preset)
            if ok:
                # Check normalized file isn't too large
                if os.path.getsize(normalized) <= MAX_LOCK_CHIME_SIZE:
                    cleanup_paths.append(normalized)
                    src = normalized
                else:
                    logger.warning("Normalized file exceeds 1MB, using un-normalized")
                    try: os.unlink(normalized)
                    except OSError: pass
            else:
                logger.warning("Normalization failed, using un-normalized: %s", err)

        # Step 5: Atomic swap
        ok, msg = atomic_chime_swap(src, filename)
        return {
            "success": ok,
            "filename": filename if ok else None,
            "error": None if ok else msg,
            "preset": preset,
            "normalized": normalize,
        }
    finally:
        for p in cleanup_paths:
            try: os.unlink(p)
            except OSError: pass


# ── Chime Listing ──

def list_chimes() -> list[dict]:
    """List all lock chime files with validation info."""
    ensure_dirs()
    chimes = []
    for f in sorted(LOCK_CHIMES_DIR.glob("*.wav")):
        if f.name.startswith("_"):
            continue
        valid, msg, info = validate_wav(f)
        chimes.append({
            "filename": f.name,
            "size_bytes": info["size_bytes"],
            "size_kb": round(info["size_bytes"] / 1024, 1),
            "duration_s": round(info["duration_s"], 2),
            "sample_rate": info["sample_rate"],
            "channels": info["channels"],
            "valid": valid,
            "message": msg,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return chimes


def delete_chime(filename: str) -> bool:
    """Delete a lock chime file."""
    path = LOCK_CHIMES_DIR / filename
    if not path.exists() or filename.startswith("_"):
        return False
    path.unlink()
    # Remove from groups
    meta = load_meta()
    for g in meta.groups.values():
        if filename in g.files:
            g.files.remove(filename)
    # Remove schedules referencing this chime
    meta.schedules = [s for s in meta.schedules if s.chime_filename != filename]
    save_meta(meta)
    return True


# ── Chime Groups ──

def load_meta() -> "ChimeMeta":
    """Load chime metadata from JSON."""
    if not CHIMES_META_FILE.exists():
        return ChimeMeta()
    try:
        data = json.loads(CHIMES_META_FILE.read_text())
        return _meta_from_dict(data)
    except Exception:
        return ChimeMeta()

def save_meta(meta: "ChimeMeta") -> None:
    """Save chime metadata to JSON atomically."""
    ensure_dirs()
    data = _meta_to_dict(meta)
    tmp = str(CHIMES_META_FILE) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CHIMES_META_FILE)

@dataclass
class ChimeMeta:
    groups: dict[str, ChimeGroup] = field(default_factory=dict)
    schedules: list[ChimeSchedule] = field(default_factory=list)
    random_config: RandomConfig = field(default_factory=RandomConfig)
    next_schedule_id: int = 1

def _meta_from_dict(d: dict) -> ChimeMeta:
    m = ChimeMeta(next_schedule_id=d.get("next_schedule_id", 1))
    for g in d.get("groups", {}).values():
        grp = ChimeGroup(id=g["id"], name=g["name"],
            description=g.get("description",""), files=g.get("files",[]),
            created_at=g.get("created_at",""), updated_at=g.get("updated_at",""))
        m.groups[grp.id] = grp
    for s in d.get("schedules", []):
        sch = ChimeSchedule(id=s.get("id",0), name=s.get("name",""),
            chime_filename=s.get("chime_filename",""),
            schedule_type=ScheduleType(s.get("schedule_type","weekly")),
            enabled=s.get("enabled",True), time=s.get("time","00:00"),
            days=s.get("days",[]), month=s.get("month",1), day=s.get("day",1),
            holiday=s.get("holiday",""), interval=s.get("interval",""),
            last_run=s.get("last_run",""), last_run_chime=s.get("last_run_chime",""))
        m.schedules.append(sch)
    rc = d.get("random_config", {})
    m.random_config = RandomConfig(enabled=rc.get("enabled",False),
        group_id=rc.get("group_id",""), last_selected=rc.get("last_selected",""),
        last_selected_at=rc.get("last_selected_at",""))
    return m

def _meta_to_dict(m: ChimeMeta) -> dict:
    return {
        "groups": {gid: {"id": g.id, "name": g.name, "description": g.description,
            "files": g.files, "created_at": g.created_at, "updated_at": g.updated_at}
            for gid, g in m.groups.items()},
        "schedules": [{"id": s.id, "name": s.name, "chime_filename": s.chime_filename,
            "schedule_type": s.schedule_type.value, "enabled": s.enabled,
            "time": s.time, "days": s.days, "month": s.month, "day": s.day,
            "holiday": s.holiday, "interval": s.interval,
            "last_run": s.last_run, "last_run_chime": s.last_run_chime}
            for s in m.schedules],
        "random_config": {"enabled": m.random_config.enabled,
            "group_id": m.random_config.group_id,
            "last_selected": m.random_config.last_selected,
            "last_selected_at": m.random_config.last_selected_at},
        "next_schedule_id": m.next_schedule_id,
    }

def list_groups() -> list[dict]:
    m = load_meta()
    return [{"id": g.id, "name": g.name, "description": g.description,
             "files": g.files, "file_count": len(g.files)} for g in m.groups.values()]

def create_group(name: str, description: str = "", files: list[str] | None = None) -> dict:
    m = load_meta()
    gid = name.lower().replace(" ", "_").replace("-", "_")
    # Avoid duplicates
    base = gid
    n = 2
    while gid in m.groups:
        gid = f"{base}_{n}"; n += 1
    now = datetime.now().isoformat()
    g = ChimeGroup(id=gid, name=name, description=description, files=files or [],
                   created_at=now, updated_at=now)
    m.groups[gid] = g
    save_meta(m)
    return {"success": True, "id": gid, "name": name}

def delete_group(group_id: str) -> dict:
    m = load_meta()
    if group_id not in m.groups:
        return {"success": False, "error": "分组不存在"}
    if m.random_config.enabled and m.random_config.group_id == group_id:
        return {"success": False, "error": "该分组正用于随机模式，请先关闭随机模式"}
    del m.groups[group_id]
    save_meta(m)
    return {"success": True}

def add_to_group(group_id: str, filename: str) -> dict:
    m = load_meta()
    if group_id not in m.groups:
        return {"success": False, "error": "分组不存在"}
    g = m.groups[group_id]
    if filename in g.files:
        return {"success": False, "error": "该音效已在分组中"}
    g.files.append(filename)
    g.updated_at = datetime.now().isoformat()
    save_meta(m)
    return {"success": True}

def select_random_chime(group_id: str = "") -> str | None:
    """Select a random chime from a group. Returns filename or None."""
    m = load_meta()
    if group_id:
        g = m.groups.get(group_id)
    elif m.random_config.enabled:
        g = m.groups.get(m.random_config.group_id)
    else:
        return None

    if not g or not g.files:
        return None

    existing = [f for f in g.files if (LOCK_CHIMES_DIR / f).exists()]
    if not existing:
        return None

    # Avoid repeating last selected
    avoid = m.random_config.last_selected
    candidates = [f for f in existing if f != avoid] if len(existing) > 1 else existing

    chosen = random.choice(candidates)
    m.random_config.last_selected = chosen
    m.random_config.last_selected_at = datetime.now().isoformat()
    save_meta(m)
    return chosen


# ── Schedules ──

def list_schedules() -> list[dict]:
    m = load_meta()
    return [_schedule_to_dict(s) for s in m.schedules]

def add_schedule(s: ChimeSchedule) -> dict:
    m = load_meta()
    s.id = m.next_schedule_id
    m.next_schedule_id += 1
    m.schedules.append(s)
    save_meta(m)
    return {"success": True, "id": s.id}

def update_schedule(schedule_id: int, updates: dict) -> dict:
    m = load_meta()
    for s in m.schedules:
        if s.id == schedule_id:
            for k, v in updates.items():
                if hasattr(s, k):
                    setattr(s, k, v)
            save_meta(m)
            return {"success": True}
    return {"success": False, "error": "排程不存在"}

def delete_schedule(schedule_id: int) -> dict:
    m = load_meta()
    m.schedules = [s for s in m.schedules if s.id != schedule_id]
    save_meta(m)
    return {"success": True}

def get_active_chime_for_now() -> str | None:
    """Determine which chime should be active right now.
    Precedence: Holiday > Date > Weekly > Recurring > Random > first available.
    """
    m = load_meta()
    now = datetime.now()
    today = now.date()
    current_time = now.strftime("%H:%M")

    # Recurring check (on_boot handled separately)
    for s in m.schedules:
        if s.schedule_type != ScheduleType.RECURRING or not s.enabled:
            continue
        if _should_run_recurring(s):
            chime = _resolve_chime(s, m)
            if chime:
                s.last_run = now.isoformat()
                s.last_run_chime = chime
                save_meta(m)
                return chime

    # Holiday check
    holiday = get_chinese_holiday(today) or get_us_holiday(today)
    for s in m.schedules:
        if s.schedule_type == ScheduleType.HOLIDAY and s.enabled and s.holiday == holiday:
            if s.time <= current_time:
                return _resolve_chime(s, m)

    # Date check
    for s in sorted(m.schedules, key=lambda x: x.time or "00:00", reverse=True):
        if s.schedule_type == ScheduleType.DATE and s.enabled:
            if s.month == today.month and s.day == today.day and s.time <= current_time:
                return _resolve_chime(s, m)

    # Weekly check
    day_names = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    today_name = day_names[today.weekday()]
    for s in sorted(m.schedules, key=lambda x: x.time or "00:00", reverse=True):
        if s.schedule_type == ScheduleType.WEEKLY and s.enabled:
            if today_name in s.days and s.time <= current_time:
                return _resolve_chime(s, m)

    # Random mode
    if m.random_config.enabled:
        chosen = select_random_chime()
        if chosen:
            return chosen

    # First available
    chimes = list_chimes()
    return chimes[0]["filename"] if chimes else None

def _resolve_chime(s: ChimeSchedule, m: ChimeMeta) -> str | None:
    if s.chime_filename == "RANDOM":
        return select_random_chime()
    return s.chime_filename if (LOCK_CHIMES_DIR / s.chime_filename).exists() else None

def _should_run_recurring(s: ChimeSchedule) -> bool:
    now = datetime.now()
    if s.interval == "on_boot":
        return True  # Caller should check boot time
    intervals = {"15min": 15, "30min": 30, "1hour": 60, "2hour": 120,
                 "4hour": 240, "6hour": 360, "12hour": 720}
    mins = intervals.get(s.interval, 60)
    if not s.last_run:
        return True
    try:
        last = datetime.fromisoformat(s.last_run)
        return (now - last).total_seconds() >= mins * 60
    except ValueError:
        return True

def _schedule_to_dict(s: ChimeSchedule) -> dict:
    return {
        "id": s.id, "name": s.name, "chime_filename": s.chime_filename,
        "schedule_type": s.schedule_type.value, "enabled": s.enabled,
        "time": s.time, "days": s.days, "month": s.month, "day": s.day,
        "holiday": s.holiday, "interval": s.interval,
        "last_run": s.last_run, "last_run_chime": s.last_run_chime,
    }


# ── Holidays ──

_CHINESE_HOLIDAYS_2026 = {
    "1/1": "元旦",
    "1/28": "除夕",
    "1/29": "春节",
    "2/12": "元宵节",
    "4/5": "清明节",
    "5/1": "劳动节",
    "5/31": "端午节",
    "10/6": "中秋节",
    "10/1": "国庆节",
    "12/21": "冬至",
}

def get_chinese_holiday(d: date) -> str | None:
    """Check static Chinese holidays. Returns holiday name or None."""
    return _CHINESE_HOLIDAYS_2026.get(f"{d.month}/{d.day}")

_US_HOLIDAYS = {
    (1,1): "New Year's Day", (2,14): "Valentine's Day", (3,17): "St. Patrick's Day",
    (7,4): "Independence Day", (10,31): "Halloween", (12,24): "Christmas Eve",
    (12,25): "Christmas Day", (12,31): "New Year's Eve",
}

def get_us_holiday(d: date) -> str | None:
    """Check US holidays (including movable). Returns holiday name or None."""
    name = _US_HOLIDAYS.get((d.month, d.day))
    if name: return name
    if d.month == 1 and d.weekday() == 0 and 15 <= d.day <= 21: return "MLK Day"
    if d.month == 2 and d.weekday() == 0 and 15 <= d.day <= 21: return "Presidents' Day"
    if d.month == 5 and d.weekday() == 0 and d.day >= 25: return "Memorial Day"
    if d.month == 9 and d.weekday() == 0 and d.day <= 7: return "Labor Day"
    if d.month == 11 and d.weekday() == 3 and 22 <= d.day <= 28: return "Thanksgiving"
    if _is_easter(d): return "Easter"
    return None

def _is_easter(d: date) -> bool:
    y = d.year; a = y % 19; b = y // 100; c = y % 100
    d2 = b // 4; e = b % 4; f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d2 - g + 15) % 30
    i = c // 4; k = c % 4; l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return d.month == (h + l - 7 * m + 114) // 31 and d.day == ((h + l - 7 * m + 114) % 31) + 1
