"""
Access Point (Hotspot) Service — offline WiFi AP for in-car access.

Manages the fallback AP that activates when WiFi is unavailable,
allowing phone/laptop connections to the Pi even without internet.

Adapted from TeslaUSB's ap_service.py and offline_ap config.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from app.config import CONFIG_PATH, config

logger = logging.getLogger("ap")

RUNTIME_FORCE_DIR = Path("/run/tjos-ap")
RUNTIME_FORCE_FILE = RUNTIME_FORCE_DIR / "force.mode"


def _ensure_runtime_dir() -> None:
    try:
        RUNTIME_FORCE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


# ── Status ──

def ap_status() -> dict:
    """Get AP status by checking if hostapd/dnsmasq are running."""
    try:
        hostapd = subprocess.run(
            ["systemctl", "is-active", "hostapd"], capture_output=True, text=True, timeout=5
        )
        dnsmasq = subprocess.run(
            ["systemctl", "is-active", "dnsmasq"], capture_output=True, text=True, timeout=5
        )
        active = hostapd.stdout.strip() == "active" or dnsmasq.stdout.strip() == "active"
    except Exception:
        active = False

    force_mode = get_force_mode()

    return {
        "active": active,
        "force_mode": force_mode,
        "ssid": config.ap.ssid if hasattr(config, "ap") else "Tesla Journey OS",
    }


# ── Force mode ──

def get_force_mode() -> str:
    """Get current AP force mode: auto, force_on, force_off."""
    _ensure_runtime_dir()
    try:
        if RUNTIME_FORCE_FILE.exists():
            return RUNTIME_FORCE_FILE.read_text().strip()
    except OSError:
        pass

    # Fall back to config
    if hasattr(config, "ap"):
        return config.ap.force_mode
    return "auto"


def set_force_mode(mode: str) -> dict:
    """Set AP force mode. Valid: auto, force_on, force_off."""
    if mode not in ("auto", "force_on", "force_off"):
        return {"success": False, "error": "Invalid mode. Use: auto, force_on, force_off"}

    _ensure_runtime_dir()
    try:
        # Write to runtime file (does not persist across reboots)
        tmp = str(RUNTIME_FORCE_FILE) + ".tmp"
        Path(tmp).write_text(mode)
        os.replace(tmp, str(RUNTIME_FORCE_FILE))
        logger.info("AP force mode set to: %s", mode)
        return {"success": True, "mode": mode}
    except OSError as e:
        return {"success": False, "error": str(e)}


# ── Config ──

def get_ap_config() -> dict:
    """Get current AP configuration."""
    if hasattr(config, "ap"):
        return {
            "ssid": config.ap.ssid,
            "passphrase": config.ap.passphrase or "",
            "channel": config.ap.channel,
            "enabled": config.ap.enabled,
            "force_mode": get_force_mode(),
        }
    return {
        "ssid": "Tesla Journey OS",
        "passphrase": "",
        "channel": 6,
        "enabled": True,
        "force_mode": "auto",
    }


def update_ap_config(ssid: str, passphrase: str) -> dict:
    """Update AP SSID and passphrase in config.yaml."""
    # Validate
    if not ssid or len(ssid) > 32:
        return {"success": False, "error": "SSID must be 1-32 characters"}
    if passphrase and (len(passphrase) < 8 or len(passphrase) > 63):
        return {"success": False, "error": "Passphrase must be 8-63 characters"}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        raw.setdefault("offline_ap", {})
        raw["offline_ap"]["ssid"] = ssid
        raw["offline_ap"]["passphrase"] = passphrase

        tmp_path = str(CONFIG_PATH) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, default_flow_style=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)

        logger.info("AP config updated: SSID=%s", ssid)
        return {"success": True, "ssid": ssid}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Connection info for captive portal ──

def get_portal_info() -> dict:
    """Get the SSID for display on the captive portal page."""
    if hasattr(config, "ap"):
        return {
            "ssid": config.ap.ssid,
            "app_name": "Tesla Journey OS",
            "tagline": "Driving Behavior Analysis Platform",
        }
    return {
        "ssid": "Tesla Journey OS",
        "app_name": "Tesla Journey OS",
        "tagline": "Driving Behavior Analysis Platform",
    }
