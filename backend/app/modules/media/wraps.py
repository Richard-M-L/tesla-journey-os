"""
Wraps & License Plates & Boombox management.

Adapted from TeslaUSB's wrap_service.py, license_plate_service.py, boombox_service.py.

Tesla requirements:
  - Wraps: PNG, 512-1024px square, < 1MB, max 10 files, max 30-char filename
  - Plates: PNG, 420x200 (NA) or 420x100 (EU), < 512KB, alphanumeric filename
  - Boombox: MP3/WAV, max 5 files
"""

import logging
import os
import shutil
import struct
import tempfile
from datetime import datetime
from pathlib import Path

from app.modules.media import WRAPS_DIR, PLATES_DIR, BOOMBOX_DIR, ensure_dirs

logger = logging.getLogger("media.wraps")


# ── PNG Validation (no PIL dependency — parses headers directly) ──

def _validate_png(file_path: str | Path) -> dict:
    """Validate a PNG file: check magic bytes, IHDR dimensions, file size.

    Returns dict with valid, width, height, error.
    """
    path = Path(file_path)
    result = {"valid": False, "width": 0, "height": 0, "error": None}

    if not path.exists():
        result["error"] = "File not found"
        return result

    try:
        with open(path, "rb") as f:
            # PNG magic: 89 50 4E 47 0D 0A 1A 0A
            magic = f.read(8)
            if magic[:4] != b"\x89PNG":
                result["error"] = "Not a PNG file"
                return result

            # IHDR chunk (must be first after magic)
            chunk_len = struct.unpack(">I", f.read(4))[0]
            chunk_type = f.read(4)
            if chunk_type != b"IHDR":
                result["error"] = "No IHDR chunk found"
                return result
            if chunk_len != 13:
                result["error"] = "Invalid IHDR size"
                return result

            ihdr = f.read(13)
            result["width"] = struct.unpack(">I", ihdr[0:4])[0]
            result["height"] = struct.unpack(">I", ihdr[4:8])[0]
            result["valid"] = True
            return result

    except Exception as e:
        result["error"] = str(e)
        return result


# ── Audio Validation ──

def _validate_audio(file_path: str | Path) -> dict:
    """Quick audio validation: check magic bytes for MP3/WAV."""
    path = Path(file_path)
    result = {"valid": False, "format": "unknown", "error": None}

    if not path.exists():
        result["error"] = "File not found"
        return result

    try:
        with open(path, "rb") as f:
            header = f.read(12)

        # WAV: RIFF header
        if header[:4] == b"RIFF":
            result["valid"] = True
            result["format"] = "wav"
            return result

        # MP3: ID3 tag or frame sync (0xFF 0xFB/0xFA/0xF3/0xF2)
        if header[:3] == b"ID3":
            result["valid"] = True
            result["format"] = "mp3"
            return result
        if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
            result["valid"] = True
            result["format"] = "mp3"
            return result

        result["error"] = "Not a valid WAV or MP3 file"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


# ── Wraps ──

def list_wraps() -> list[dict]:
    ensure_dirs()
    wraps = []
    for f in sorted(WRAPS_DIR.glob("*.png")):
        validation = _validate_png(f)
        wraps.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "width": validation["width"],
            "height": validation["height"],
            "valid": validation["valid"],
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return wraps


def upload_wrap(file_path: str | Path, filename: str | None = None) -> dict:
    ensure_dirs()
    src = Path(file_path)
    name = filename or src.name

    # Validate filename
    if len(name) > 30:
        return {"success": False, "error": "Filename must be 30 characters or less"}
    if not name.lower().endswith(".png"):
        return {"success": False, "error": "Must be a PNG file"}

    # Validate PNG
    validation = _validate_png(src)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    w, h = validation["width"], validation["height"]
    if w < 512 or w > 1024 or h < 512 or h > 1024:
        return {"success": False,
                "error": f"Dimensions {w}x{h} outside valid range (512-1024px)"}

    # File size
    if src.stat().st_size > 1024 * 1024:
        return {"success": False, "error": "File must be under 1 MB"}

    # Count limit
    existing = list(WRAPS_DIR.glob("*.png"))
    if len(existing) >= 10:
        return {"success": False, "error": "Maximum 10 wraps. Delete one first."}

    # Copy
    dest = WRAPS_DIR / name
    tmp = str(dest) + ".tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, str(dest))
    return {"success": True, "filename": name, "size_bytes": dest.stat().st_size}


def delete_wrap(filename: str) -> bool:
    path = WRAPS_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False


# ── License Plates ──

def list_plates() -> list[dict]:
    ensure_dirs()
    plates = []
    for f in sorted(PLATES_DIR.glob("*.png")):
        validation = _validate_png(f)
        ok_dims = ((validation["width"] == 420 and validation["height"] in (100, 200)))
        plates.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "width": validation["width"],
            "height": validation["height"],
            "valid_dims": ok_dims,
            "region": "EU" if validation["height"] == 100 else "NA" if validation["height"] == 200 else "Unknown",
            "valid": validation["valid"],
        })
    return plates


def upload_plate(file_path: str | Path, filename: str | None = None) -> dict:
    ensure_dirs()
    src = Path(file_path)
    name = filename or src.name

    # Validate filename: alphanumeric, no spaces/dashes/underscores, max 32 chars
    stem = Path(name).stem
    if len(stem) > 32:
        return {"success": False, "error": "Filename must be 32 characters or less"}
    if not stem.replace("-", "").replace("_", "").isalnum():
        return {"success": False, "error": "Filename must be alphanumeric only"}

    if not name.lower().endswith(".png"):
        return {"success": False, "error": "Must be a PNG file"}

    validation = _validate_png(src)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"]}

    w, h = validation["width"], validation["height"]
    if w != 420 or h not in (100, 200):
        return {"success": False,
                "error": f"Must be 420x200 (NA) or 420x100 (EU), got {w}x{h}"}

    if src.stat().st_size > 512 * 1024:
        return {"success": False, "error": "File must be under 512 KB"}

    dest = PLATES_DIR / name
    tmp = str(dest) + ".tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, str(dest))
    return {"success": True, "filename": name, "region": "EU" if h == 100 else "NA"}


def delete_plate(filename: str) -> bool:
    path = PLATES_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False


# ── Boombox ──

def list_boombox() -> list[dict]:
    ensure_dirs()
    files = []
    for f in sorted(BOOMBOX_DIR.glob("*")):
        if not f.is_file():
            continue
        validation = _validate_audio(f)
        files.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "format": validation["format"],
            "valid": validation["valid"],
        })
    return files


def upload_boombox(file_path: str | Path) -> dict:
    ensure_dirs()
    src = Path(file_path)

    validation = _validate_audio(src)
    if not validation["valid"]:
        return {"success": False, "error": validation["error"] or "Invalid audio file"}

    # 5-file limit
    existing = [f for f in BOOMBOX_DIR.iterdir() if f.is_file()]
    if len(existing) >= 5 and not (BOOMBOX_DIR / src.name).exists():
        return {"success": False, "error": "Maximum 5 boombox sounds. Delete one first."}

    dest = BOOMBOX_DIR / src.name
    tmp = str(dest) + ".tmp"
    shutil.copy2(src, tmp)
    os.replace(tmp, str(dest))
    return {"success": True, "filename": src.name, "format": validation["format"]}


def delete_boombox(filename: str) -> bool:
    path = BOOMBOX_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False
