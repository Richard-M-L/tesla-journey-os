"""
Media Manager — manages Tesla vehicle customization files.

Replicates the USB mass-storage features from TeslaUSB without
requiring a physical USB gadget connection:
  - Lock Chimes  (.wav files with scheduling)
  - Light Shows  (.fseq + audio ZIP files)
  - Music        (.mp3, .flac, .wav, .aac, .m4a)
  - Boombox      (5 custom MP3/WAV sounds)
  - Wraps        (PNG car wrap images, 512-1024px)
  - License Plates (PNG plate images, 420x200/420x100)

All files are stored in data/media/ and can be exported to a
USB drive for the Tesla vehicle to read.
"""

from pathlib import Path
from app.config import PROJECT_ROOT

MEDIA_DIR = Path(PROJECT_ROOT) / "data" / "media"

# Subdirectories match Tesla's expected USB layout
LOCK_CHIMES_DIR = MEDIA_DIR / "LockChimes"
LIGHT_SHOW_DIR = MEDIA_DIR / "LightShow"
MUSIC_DIR = MEDIA_DIR / "Music"
BOOMBOX_DIR = MEDIA_DIR / "Boombox"
WRAPS_DIR = MEDIA_DIR / "Wraps"
PLATES_DIR = MEDIA_DIR / "LicensePlates"

ALL_MEDIA_DIRS = [LOCK_CHIMES_DIR, LIGHT_SHOW_DIR, MUSIC_DIR, BOOMBOX_DIR, WRAPS_DIR, PLATES_DIR]


def ensure_dirs() -> None:
    """Create all media directories if they don't exist."""
    for d in ALL_MEDIA_DIRS:
        d.mkdir(parents=True, exist_ok=True)
