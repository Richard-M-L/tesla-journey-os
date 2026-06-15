"""
WiFi Service — network scanning, connection management, saved networks.

Uses NetworkManager (nmcli) on Linux. Falls back gracefully on non-Linux.
Adapted from TeslaUSB's wifi_service.py.
"""

import json
import logging
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger("wifi")

WIFI_STATUS_FILE = Path("/tmp/tjos_wifi_status.json")
_CONNECT_LOCK = threading.Lock()


def _nmcli(args: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Run an nmcli command, returns CompletedProcess or a stub with empty stdout."""
    try:
        return subprocess.run(
            ["nmcli"] + args, capture_output=True, text=True, timeout=timeout
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="nmcli unavailable")


# ── Status ──

def get_current_connection() -> dict:
    """Get current WiFi connection info."""
    result = _nmcli(["-t", "-f", "ACTIVE,SSID,SIGNAL", "dev", "wifi"])
    if result.returncode != 0 or not result.stdout:
        return {"connected": False, "ssid": None, "signal": None}

    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 3 and parts[0] == "yes":
            return {
                "connected": True,
                "ssid": parts[1],
                "signal": int(parts[2]) if parts[2].isdigit() else None,
            }
    return {"connected": False, "ssid": None, "signal": None}


# ── Scan ──

def scan_networks(rescan: bool = True) -> list[dict]:
    """Scan for available WiFi networks, sorted by signal strength."""
    if rescan:
        _nmcli(["dev", "wifi", "rescan"], timeout=30)

    result = _nmcli(["-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"])

    networks: dict[str, dict] = {}
    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) < 3 or not parts[0].strip():
            continue
        ssid = parts[0].strip()
        signal = int(parts[1]) if parts[1].strip().isdigit() else 0
        security = parts[2].strip()

        if ssid not in networks or signal > networks[ssid]["signal"]:
            networks[ssid] = {
                "ssid": ssid,
                "signal": signal,
                "security": security,
                "secured": security != "",
            }

    return sorted(networks.values(), key=lambda n: n["signal"], reverse=True)


# ── Saved networks ──

def get_saved_networks() -> list[dict]:
    """List all saved WiFi connections."""
    result = _nmcli(["-t", "-f", "NAME,TYPE,AUTOCONNECT-PRIORITY", "connection"])

    saved = []
    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, conn_type, priority = parts[0], parts[1], parts[2]
        if conn_type != "802-11-wireless":
            continue

        # Get SSID
        ssid_result = _nmcli(["-t", "-f", "802-11-wireless.ssid", "connection", "show", name])
        ssid = ""
        if ssid_result.stdout:
            ssid = ssid_result.stdout.strip()

        saved.append({
            "name": name,
            "ssid": ssid,
            "priority": int(priority) if priority.strip().lstrip("-").isdigit() else 0,
        })

    return sorted(saved, key=lambda n: n["priority"], reverse=True)


# ── Connect ──

def connect_to_ssid(ssid: str, password: str) -> dict:
    """Connect to a WiFi network. Returns success/error."""
    with _CONNECT_LOCK:
        # Validate inputs
        if not ssid or len(ssid) > 32:
            return {"success": False, "error": "SSID must be 1-32 characters"}
        if password and len(password) < 8:
            return {"success": False, "error": "Password must be at least 8 characters"}

        # Remove existing connection with same SSID if exists
        existing = _find_connection_by_ssid(ssid)
        if existing:
            _nmcli(["connection", "delete", existing])

        # Create new connection
        result = _nmcli([
            "device", "wifi", "connect", ssid,
            "password", password,
        ])

        if result.returncode == 0:
            _promote_connection(ssid)
            _write_status({"success": True, "ssid": ssid})
            return {"success": True, "ssid": ssid}
        else:
            err = result.stderr.strip() or "Connection failed"
            _write_status({"success": False, "error": err})
            return {"success": False, "error": err}


def forget_network(connection_name: str) -> dict:
    """Remove a saved WiFi network."""
    saved = get_saved_networks()
    if len(saved) <= 1:
        return {"success": False, "error": "Cannot delete the only saved network"}

    result = _nmcli(["connection", "delete", connection_name])
    if result.returncode == 0:
        return {"success": True}
    return {"success": False, "error": result.stderr.strip() or "Delete failed"}


# ── Helpers ──

def _find_connection_by_ssid(ssid: str) -> str | None:
    """Find a connection name by SSID."""
    for net in get_saved_networks():
        if net["ssid"] == ssid:
            return net["name"]
    return None


def _promote_connection(ssid: str) -> None:
    """Give the newly connected network highest priority."""
    name = _find_connection_by_ssid(ssid)
    if not name:
        return
    _nmcli(["connection", "modify", name, "connection.autoconnect-priority", "100"])


def _write_status(data: dict) -> None:
    """Write status to the temp file for polling."""
    try:
        WIFI_STATUS_FILE.write_text(json.dumps(data))
    except OSError:
        pass


def get_status() -> dict:
    """Get combined WiFi status."""
    current = get_current_connection()
    try:
        if WIFI_STATUS_FILE.exists():
            last_op = json.loads(WIFI_STATUS_FILE.read_text())
        else:
            last_op = {}
    except (OSError, json.JSONDecodeError):
        last_op = {}

    return {
        "connected": current["connected"],
        "ssid": current["ssid"],
        "signal": current["signal"],
        "last_operation": last_op,
    }
