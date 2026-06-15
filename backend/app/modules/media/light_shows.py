"""
Light Show Management — upload, manage, and download Tesla light show files.

Adapted from TeslaUSB's light_show_service.py.

Tesla requirements:
  - A light show consists of a .fseq file + optional .mp3/.wav audio
  - Multiple files with the same base name form one "show"
  - Stored in /LightShow/ on the USB drive
  - ZIP archives can contain multiple shows (extracted on upload)
"""

import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from app.modules.media import LIGHT_SHOW_DIR, ensure_dirs

logger = logging.getLogger("media.light_shows")


def list_shows() -> list[dict]:
    """List all light shows, grouped by base name."""
    ensure_dirs()
    shows: dict[str, list[dict]] = {}

    for f in sorted(LIGHT_SHOW_DIR.iterdir()):
        if f.is_dir():
            continue
        base = _base_name(f.name)
        if base not in shows:
            shows[base] = []
        shows[base].append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            "ext": f.suffix.lower(),
        })

    result = []
    for name, files in shows.items():
        has_fseq = any(f["ext"] == ".fseq" for f in files)
        has_audio = any(f["ext"] in (".mp3", ".wav") for f in files)
        result.append({
            "name": name,
            "files": files,
            "file_count": len(files),
            "has_fseq": has_fseq,
            "has_audio": has_audio,
            "valid": has_fseq,  # .fseq is required
            "total_size_bytes": sum(f["size_bytes"] for f in files),
        })

    return sorted(result, key=lambda s: s["name"])


def upload_zip(zip_path: str | Path) -> dict:
    """Extract a ZIP file containing light show files.

    Recursively finds .fseq, .mp3, .wav files and copies them to LightShow/.

    Returns dict with success status and list of extracted files.
    """
    ensure_dirs()
    zip_path = Path(zip_path)
    extracted = []
    errors = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for member in zf.namelist():
                # Skip directories
                if member.endswith("/"):
                    continue

                fname = Path(member).name
                ext = Path(fname).suffix.lower()

                if ext not in (".fseq", ".mp3", ".wav"):
                    continue

                # Extract to temp, then copy to LightShow dir
                try:
                    dest = LIGHT_SHOW_DIR / fname
                    with zf.open(member) as src:
                        # Atomic write
                        tmp = str(dest) + ".tmp"
                        with open(tmp, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        os.replace(tmp, str(dest))
                    extracted.append(fname)
                except Exception as e:
                    errors.append(f"{fname}: {e}")

        return {
            "success": len(extracted) > 0,
            "extracted": extracted,
            "count": len(extracted),
            "errors": errors,
        }
    except zipfile.BadZipFile:
        return {"success": False, "error": "Invalid ZIP file", "extracted": []}
    except Exception as e:
        return {"success": False, "error": str(e), "extracted": []}


def upload_single(file_path: str | Path) -> dict:
    """Upload a single light show file (.fseq, .mp3, or .wav)."""
    ensure_dirs()
    src = Path(file_path)
    fname = src.name
    ext = src.suffix.lower()

    if ext not in (".fseq", ".mp3", ".wav"):
        return {"success": False, "error": f"Unsupported format: {ext}. Use .fseq, .mp3, or .wav"}

    dest = LIGHT_SHOW_DIR / fname
    try:
        tmp = str(dest) + ".tmp"
        shutil.copy2(src, tmp)
        os.replace(tmp, str(dest))
        return {
            "success": True,
            "filename": fname,
            "size_bytes": dest.stat().st_size,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_show(name: str) -> int:
    """Delete all files belonging to a light show (by base name).

    Returns the number of files deleted.
    """
    ensure_dirs()
    count = 0
    for f in LIGHT_SHOW_DIR.iterdir():
        if f.is_file() and _base_name(f.name) == name:
            f.unlink()
            count += 1
    return count


def download_as_zip(name: str) -> str | None:
    """Create a ZIP file of a light show. Returns path to the ZIP, or None."""
    files = [f for f in LIGHT_SHOW_DIR.iterdir()
             if f.is_file() and _base_name(f.name) == name]

    if not files:
        return None

    zip_path = LIGHT_SHOW_DIR / f"{name}.zip"
    try:
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.name)
        return str(zip_path)
    except Exception:
        logger.exception("Failed to create light show ZIP")
        return None


def _base_name(filename: str) -> str:
    """Get the base name without extension. 'show1.fseq' -> 'show1'"""
    # Handle double extensions like .lightshow.fseq
    name = Path(filename).stem
    if name.endswith(".lightshow"):
        name = Path(name).stem
    return name
