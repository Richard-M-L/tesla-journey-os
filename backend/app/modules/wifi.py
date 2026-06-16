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
    """List all saved WiFi connections enriched with signal, active, in_range."""
    result = _nmcli(["-t", "-f", "NAME,TYPE,AUTOCONNECT-PRIORITY", "connection"])

    # Get active connection name + scan results for enrichment
    active_name = _get_active_wlan0_connection()
    scan_results = {n["ssid"]: n for n in scan_networks(rescan=False)} if active_name else {}

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

        # Enrich
        active = name == active_name
        in_range = ssid in scan_results
        signal = scan_results[ssid]["signal"] if in_range else None

        saved.append({
            "name": name,
            "ssid": ssid,
            "priority": int(priority) if priority.strip().lstrip("-").isdigit() else 0,
            "active": active,
            "in_range": in_range,
            "signal": signal,
        })

    return sorted(saved, key=lambda n: n["priority"], reverse=True)


# ── Connect ──

def connect_to_ssid(ssid: str, password: str) -> dict:
    """Connect to a WiFi network with failsafe: revert + AP fallback.

    1. Save current connection for revert
    2. Try to connect to the new network
    3. If fails, revert to previous connection
    4. If revert fails too, start fallback AP
    """
    with _CONNECT_LOCK:
        # Validate inputs
        if not ssid or len(ssid) > 32:
            return {"success": False, "error": "SSID 须 1-32 个字符"}
        if password and (len(password) < 8 or len(password) > 63):
            return {"success": False, "error": "密码须 8-63 个字符"}

        # Save current active connection for rollback
        prev_connection = _get_active_wlan0_connection()
        logger.info("Current connection: %s, connecting to: %s", prev_connection, ssid)

        # Remove existing connection with same SSID
        existing = _find_connection_by_ssid(ssid)
        if existing:
            _nmcli(["connection", "delete", existing])

        # Try to connect (with retries)
        connected = False
        for attempt in range(1, 4):
            result = _nmcli([
                "device", "wifi", "connect", ssid,
                "password", password,
            ], timeout=30)
            if result.returncode == 0:
                connected = True
                break
            logger.warning("Connect attempt %d/3 failed, retrying...", attempt)
            time_mod.sleep(3)

        if connected:
            # Verify IPv4
            if _wlan0_has_ipv4():
                _promote_connection(ssid)
                _write_status({"success": True, "ssid": ssid})
                return {"success": True, "ssid": ssid, "verified": True}
            else:
                logger.warning("Connected but no IPv4 — waiting...")
                time_mod.sleep(5)
                if _wlan0_has_ipv4():
                    _promote_connection(ssid)
                    return {"success": True, "ssid": ssid, "verified": True}

        # ── FAILSAFE: revert to previous connection ──
        logger.error("Connection to %s failed, reverting to %s", ssid, prev_connection)
        if prev_connection:
            revert = _nmcli(["connection", "up", prev_connection], timeout=20)
            if revert.returncode == 0 and _wlan0_has_ipv4():
                _write_status({"success": False, "error": f"连接 {ssid} 失败，已恢复到 {prev_connection}", "reverted": True})
                return {"success": False, "error": f"连接失败，已恢复到 {prev_connection}", "reverted": True}

        # ── LAST RESORT: start AP fallback ──
        logger.warning("Revert failed, starting fallback AP")
        _start_fallback_ap()
        _write_status({"success": False, "error": f"连接 {ssid} 失败，已启动热点", "ap_started": True})
        return {"success": False, "error": "连接失败，已启动离线热点", "ap_started": True}


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
    """Give the newly connected network highest priority, decrement others."""
    name = _find_connection_by_ssid(ssid)
    if not name:
        return
    _nmcli(["connection", "modify", name, "connection.autoconnect-priority", "100"])
    # Decrement other wireless connections
    for net in get_saved_networks():
        if net["name"] != name:
            new_pri = max(0, net["priority"] - 10)
            _nmcli(["connection", "modify", net["name"], "connection.autoconnect-priority", str(new_pri)])

def _get_active_wlan0_connection() -> str | None:
    """Get the name of the currently active connection on wlan0."""
    result = _nmcli(["-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 2 and parts[1].strip() == "wlan0":
            return parts[0].strip()
    return None

def _wlan0_has_ipv4() -> bool:
    """Check if wlan0 has a valid IPv4 address."""
    import subprocess as sp
    try:
        r = sp.run(["ip", "-4", "-br", "addr", "show", "wlan0"],
                   capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False

def _start_fallback_ap() -> None:
    """Start the offline access point as a connectivity fallback."""
    try:
        from app.modules.ap import set_force_mode
        set_force_mode("force_on")
        logger.info("Fallback AP started")
    except Exception:
        logger.exception("Failed to start fallback AP")

def _get_connection_signal(connection_name: str) -> int | None:
    """Get RSSI signal strength for an active connection."""
    result = _nmcli(["-t", "-f", "IN-USE,SIGNAL", "dev", "wifi"])
    for line in result.stdout.strip().split("\n"):
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == "*":
            try: return int(parts[1])
            except ValueError: pass
    return None


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
