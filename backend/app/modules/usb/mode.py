"""
Mode detection for USB gadget state.

Determines whether the system is in:
  - present: USB gadget active, car can access drives
  - edit:    USB gadget stopped, Pi can modify drives
  - unknown: cannot determine

Ported from TeslaUSB's mode_service.py.
"""

import logging
from pathlib import Path

logger = logging.getLogger("usb.mode")

STATE_FILE = Path("/var/run/tjos_usb_mode")
GADGET_BASE = Path("/sys/kernel/config/usb_gadget")
RO_MOUNT_DIR = Path("/mnt/tjos_gadget")

MODE_DISPLAY = {
    "present": ("Present", "text-green-400"),
    "edit": ("Edit", "text-blue-400"),
    "unknown": ("Unknown", "text-gray-500"),
}


def detect_mode() -> str:
    """Detect the current USB gadget mode from system state."""
    # Check ConfigFS gadget
    try:
        for gadget_dir in GADGET_BASE.iterdir():
            udc_file = gadget_dir / "UDC"
            if udc_file.exists():
                content = udc_file.read_text().strip()
                if content:
                    logger.debug("Detected present mode via ConfigFS UDC: %s", content)
                    return "present"

            # Check for LUN files with backing store
            for lun_file in gadget_dir.glob("functions/mass_storage.*/lun.*/file"):
                try:
                    if lun_file.read_text().strip():
                        logger.debug("Detected present mode via LUN backing file")
                        return "present"
                except OSError:
                    continue
    except OSError:
        pass

    # Check for RO mounts (indicates present mode with local access)
    try:
        if RO_MOUNT_DIR.exists():
            for mp in RO_MOUNT_DIR.glob("part*-ro"):
                if mp.is_mount():
                    logger.debug("Detected present mode via RO mount: %s", mp)
                    return "present"
    except OSError:
        pass

    # Check state file
    try:
        if STATE_FILE.exists():
            mode = STATE_FILE.read_text().strip().lower()
            if mode in ("present", "edit"):
                return mode
    except OSError:
        pass

    return "unknown"


def current_mode() -> str:
    """Read current mode from state file, falling back to detection."""
    try:
        if STATE_FILE.exists():
            token = STATE_FILE.read_text().strip().lower()
            if token in ("present", "edit"):
                return token
    except OSError:
        pass

    return detect_mode()


def is_present() -> bool:
    return current_mode() == "present"


def is_edit() -> bool:
    return current_mode() == "edit"
