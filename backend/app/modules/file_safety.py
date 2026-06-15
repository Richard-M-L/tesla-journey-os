"""
File Safety Guards — prevent accidental deletion of critical files.

Adapted from TeslaUSB's file_safety.py.

Protection rules:
  - *.img files: USB gadget disk images — NEVER delete
  - *.db files: SQLite databases — NEVER delete via cleanup
  - *.db-wal / *.db-shm: Database journal files — NEVER delete

All cleanup/retention operations must pass through safe_delete().
"""

import os
from pathlib import Path

from app.config import PROJECT_ROOT

# Patterns that must never be deleted
PROTECTED_PATTERNS = [
    "*.img",
    "*.db",
    "*.db-wal",
    "*.db-shm",
    "*.db-journal",
    "*.key",
    "*.pem",
    "config.yaml",
    "config.yml",
    "*.env",
]

# Additional protected paths (relative to project root)
PROTECTED_PATHS = [
    "data/images",
    "deploy",
]


def is_protected_file(path: str | Path) -> bool:
    """Check if a file is protected from deletion.

    Returns True if the file matches any protected pattern or path.
    """
    p = Path(path)

    # Check filename patterns
    for pattern in PROTECTED_PATTERNS:
        if p.match(pattern):
            return True

    # Check protected parent directories
    try:
        rel = p.relative_to(PROJECT_ROOT)
        for protected in PROTECTED_PATHS:
            if str(rel).startswith(protected):
                return True
    except ValueError:
        pass  # Not under project root

    return False


def safe_delete(path: str | Path) -> tuple[bool, str]:
    """Safely delete a file if it's not protected.

    Returns (success, reason).
      - (True, "deleted"): File was deleted
      - (True, "not_found"): File didn't exist
      - (False, "protected: ..."): File is protected, deletion refused
      - (False, "error: ..."): OS error during deletion
    """
    p = Path(path)

    if not p.exists():
        return True, "not_found"

    if is_protected_file(p):
        return False, f"protected: {p.name}"

    try:
        p.unlink()
        return True, "deleted"
    except OSError as e:
        return False, f"error: {e}"


def safe_delete_video(path: str | Path) -> tuple[bool, str]:
    """Safely delete a video file and its sidecar cache.

    Only allows deletion of .mp4 files and .sei.json sidecars.
    Refuses to delete anything under /data/images/ or .img files.
    """
    p = Path(path)

    if not p.suffix.lower() in (".mp4", ".json"):
        return False, f"protected: not a video file ({p.suffix})"

    if is_protected_file(p):
        return False, f"protected: {p.name}"

    try:
        if p.exists():
            p.unlink()
        # Also delete sidecar if it exists
        sidecar = p.with_suffix(".sei.json")
        if sidecar.exists():
            sidecar.unlink()
        return True, "deleted"
    except OSError as e:
        return False, f"error: {e}"


def safe_rmtree(path: str | Path) -> tuple[bool, str]:
    """Safely delete a directory tree, refusing on protected paths."""
    p = Path(path)

    if not p.exists():
        return True, "not_found"

    if is_protected_file(p):
        return False, f"protected: {p.name}"

    # Double-check: never delete the data/images directory
    try:
        rel = Path(path).resolve().relative_to(PROJECT_ROOT.resolve())
        if any(part == "images" for part in rel.parts):
            return False, "protected: images directory"
    except ValueError:
        pass

    import shutil
    try:
        shutil.rmtree(p)
        return True, "deleted"
    except OSError as e:
        return False, f"error: {e}"
