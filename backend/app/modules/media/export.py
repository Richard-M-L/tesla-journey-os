"""
Media Export — sync managed media files to a USB drive for Tesla vehicle use.

When the user plugs in a USB drive, this module copies:
  LockChimes/   → USB:/LockChimes/
  LightShow/    → USB:/LightShow/
  Music/        → USB:/Music/
  Boombox/      → USB:/Boombox/
  Wraps/        → USB:/Wraps/
  LicensePlates/ → USB:/LicensePlates/

Tesla expects specific directory names at the root of the USB drive.
"""

import logging
import os
import shutil
from pathlib import Path

from app.modules.media import (
    LOCK_CHIMES_DIR, LIGHT_SHOW_DIR, MUSIC_DIR,
    BOOMBOX_DIR, WRAPS_DIR, PLATES_DIR, ensure_dirs,
)

logger = logging.getLogger("media.export")

# Tesla's expected directory names on USB
EXPORT_MAP = {
    LOCK_CHIMES_DIR: "LockChimes",
    LIGHT_SHOW_DIR: "LightShow",
    MUSIC_DIR: "Music",
    BOOMBOX_DIR: "Boombox",
    WRAPS_DIR: "Wraps",
    PLATES_DIR: "LicensePlates",
}


def list_usb_drives() -> list[dict]:
    """Detect mounted USB drives. Returns list of {path, label, free_gb}."""
    drives = []

    # Linux: check /media/ and /mnt/
    for base in ["/media", "/mnt"]:
        base_path = Path(base)
        if not base_path.exists():
            continue
        for user_dir in base_path.iterdir():
            if not user_dir.is_dir():
                continue
            # Check if it's a mount point (has files, not a system dir)
            try:
                contents = list(user_dir.iterdir())
                if contents:
                    usage = shutil.disk_usage(str(user_dir))
                    drives.append({
                        "path": str(user_dir),
                        "label": user_dir.name,
                        "free_gb": round(usage.free / (1024**3), 1),
                        "total_gb": round(usage.total / (1024**3), 1),
                    })
            except (OSError, PermissionError):
                continue

    # Windows: check common drive letters
    import sys
    if sys.platform == "win32":
        import string
        from ctypes import windll
        for letter in string.ascii_uppercase[2:]:  # Skip A:, B:
            drive = f"{letter}:\\"
            try:
                if os.path.exists(drive):
                    usage = shutil.disk_usage(drive)
                    # Only include removable drives (type 2)
                    drives.append({
                        "path": drive,
                        "label": f"Drive {letter}:",
                        "free_gb": round(usage.free / (1024**3), 1),
                        "total_gb": round(usage.total / (1024**3), 1),
                    })
            except OSError:
                continue

    return drives


def get_export_preview() -> dict:
    """Preview what would be exported: count of files per category, total size."""
    ensure_dirs()
    preview: dict[str, dict] = {}

    total_files = 0
    total_bytes = 0

    for src_dir, dest_name in EXPORT_MAP.items():
        if not src_dir.exists():
            continue
        files = [f for f in src_dir.iterdir() if f.is_file()]
        if not files:
            continue

        size = sum(f.stat().st_size for f in files)
        preview[dest_name] = {
            "file_count": len(files),
            "size_mb": round(size / (1024 * 1024), 1),
            "files": [f.name for f in sorted(files)],
        }
        total_files += len(files)
        total_bytes += size

    return {
        "categories": preview,
        "total_files": total_files,
        "total_size_mb": round(total_bytes / (1024 * 1024), 1),
    }


def export_to_usb(target_path: str, dry_run: bool = False) -> dict:
    """Export all managed media files to a USB drive.

    Args:
        target_path: Root path of the USB drive (e.g., /media/pi/USBDRIVE)
        dry_run: If True, only preview — don't actually copy.

    Returns dict with results per category.
    """
    ensure_dirs()
    target = Path(target_path)

    if not target.exists():
        return {"success": False, "error": f"Target path not found: {target_path}"}

    results: dict[str, dict] = {}
    total_copied = 0
    total_bytes = 0
    errors = []

    for src_dir, dest_name in EXPORT_MAP.items():
        if not src_dir.exists():
            continue

        files = [f for f in src_dir.iterdir() if f.is_file()]
        if not files:
            continue

        dest_dir = target / dest_name
        copied = 0
        dest_bytes = 0

        if not dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            dest_file = dest_dir / f.name
            try:
                if not dry_run:
                    # Only copy if source is newer
                    if dest_file.exists() and dest_file.stat().st_mtime >= f.stat().st_mtime:
                        continue
                    shutil.copy2(f, dest_file)
                copied += 1
                dest_bytes += f.stat().st_size
            except OSError as e:
                errors.append(f"{dest_name}/{f.name}: {e}")

        results[dest_name] = {
            "copied": copied,
            "size_mb": round(dest_bytes / (1024 * 1024), 1),
            "file_count": len(files),
        }
        total_copied += copied
        total_bytes += dest_bytes

    return {
        "success": len(errors) == 0,
        "dry_run": dry_run,
        "target": str(target),
        "total_copied": total_copied,
        "total_size_mb": round(total_bytes / (1024 * 1024), 1),
        "results": results,
        "errors": errors if errors else None,
    }
