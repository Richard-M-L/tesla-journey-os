"""
System Watchdog — hardware watchdog feeding, archive health, safe mode.

Three subsystems adapted from TeslaUSB:

1. Hardware Watchdog (/dev/watchdog)
   - Feeds the Linux hardware watchdog at regular intervals
   - If the process hangs, the Pi reboots automatically
   - Essential for unattended in-car operation

2. Archive Watchdog
   - Monitors archive queue health
   - Detects "lost clips" (files Tesla rotated out before archiving)
   - Tracks drain rates and ETA

3. Safe Mode
   - Tracks rapid reboots via a state file
   - 3+ reboots in 10 minutes → safe mode (skip all services, keep SSH+AP)
   - Prevents death-spiral on corrupted SD card
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("watchdog")

# Hardware watchdog device
WATCHDOG_DEVICE = Path("/dev/watchdog")
WATCHDOG_INTERVAL = 10  # seconds between feeds

# Safe mode file
SAFE_MODE_FILE = Path("/var/run/tjos_safe_mode")
REBOOT_TRACKER = Path("/var/run/tjos_reboots")

# Safe mode thresholds
SAFE_MODE_REBOOT_COUNT = 3
SAFE_MODE_WINDOW_MINUTES = 10


# ── Hardware Watchdog ──

class HardwareWatchdog:
    """Feeds the Linux /dev/watchdog to prevent system reboot.

    The Pi's hardware watchdog reboots the system if not fed within
    ~15 seconds (hardware default). This class opens the device and
    writes to it at regular intervals.

    Usage:
        wd = HardwareWatchdog()
        wd.start()
        # ... application runs ...
        wd.stop()  # Graceful stop (writes magic 'V' to disable)
    """

    def __init__(self):
        self._fd = None
        self._running = False

    def start(self) -> bool:
        """Open the watchdog device and begin feeding."""
        if not WATCHDOG_DEVICE.exists():
            logger.info("No hardware watchdog device found — skipping")
            return False

        try:
            # Open with magic close flag (write 'V' to disable on close)
            self._fd = os.open(str(WATCHDOG_DEVICE), os.O_WRONLY)
            self._running = True
            logger.info("Hardware watchdog started (feed every %ds)", WATCHDOG_INTERVAL)
            self._feed()
            return True
        except OSError as e:
            logger.warning("Cannot open watchdog device: %s", e)
            return False

    def feed(self) -> None:
        """Feed the watchdog. Call this regularly or the Pi reboots."""
        if self._fd is not None:
            try:
                os.write(self._fd, b"\0")
            except OSError:
                logger.error("Watchdog feed failed — system may reboot!")

    def stop(self) -> None:
        """Gracefully stop the watchdog (writes magic 'V' to disable)."""
        if self._fd is None:
            return
        try:
            os.write(self._fd, b"V")
            os.close(self._fd)
            logger.info("Hardware watchdog stopped")
        except OSError:
            pass
        finally:
            self._fd = None
            self._running = False

    def _feed(self) -> None:
        """Feed loop — runs in a background thread."""
        import threading

        def _loop():
            while self._running:
                self.feed()
                time.sleep(WATCHDOG_INTERVAL)

        t = threading.Thread(target=_loop, daemon=True, name="watchdog-feeder")
        t.start()


# ── Archive Watchdog ──

class ArchiveWatchdog:
    """Monitors archive health: lost clips, drain rates, queue depths.

    "Lost clips" are dashcam videos the Tesla rotated/deleted before
    the archive worker could copy them to durable storage.

    Adapted from TeslaUSB's archive_watchdog.py.
    """

    def __init__(self):
        self._lost_clip_count = 0
        self._last_check = time.time()
        self._drain_rate = 0.0  # clips per second
        self._queue_depth_history: list[float] = []
        self._alerts: list[dict] = []

    def record_lost_clip(self, file_path: str) -> None:
        """Record that a clip was lost (Tesla rotated it out before archiving)."""
        self._lost_clip_count += 1
        logger.warning("Lost clip: %s (total lost: %d)", file_path, self._lost_clip_count)

    def record_drain(self, clip_count: int, elapsed_seconds: float) -> None:
        """Record the drain rate for ETA calculation."""
        if elapsed_seconds > 0:
            rate = clip_count / elapsed_seconds
            # Weighted average: 70% old, 30% new
            if self._drain_rate == 0:
                self._drain_rate = rate
            else:
                self._drain_rate = self._drain_rate * 0.7 + rate * 0.3

    def check(self, queue_depth: int, worker_running: bool) -> dict:
        """Run a health check and return status.

        Returns dict suitable for system health API.
        """
        now = time.time()
        self._queue_depth_history.append((now, queue_depth))
        # Keep last 60 data points
        if len(self._queue_depth_history) > 60:
            self._queue_depth_history = self._queue_depth_history[-60:]

        severity = "ok"
        alerts = []

        # Lost clips in last 24 hours
        if self._lost_clip_count > 0:
            severity = "warn"
            alerts.append({
                "severity": "warn",
                "message": f"{self._lost_clip_count} clips lost in last 24h",
            })

        # Queue growing faster than draining
        if len(self._queue_depth_history) >= 3:
            recent = [d for _, d in self._queue_depth_history[-3:]]
            if recent[-1] > recent[0] and recent[-1] > 10:
                severity = "warn"
                alerts.append({
                    "severity": "warn",
                    "message": f"Archive queue growing ({recent[0]} → {recent[-1]})",
                })

        # Worker not running but queue has items
        if not worker_running and queue_depth > 0:
            severity = "error"
            alerts.append({
                "severity": "error",
                "message": f"Archive worker stopped with {queue_depth} items queued",
            })

        # ETA
        eta_seconds = None
        if self._drain_rate > 0 and queue_depth > 0:
            eta_seconds = queue_depth / self._drain_rate

        return {
            "severity": severity,
            "lost_clips_24h": self._lost_clip_count,
            "queue_depth": queue_depth,
            "worker_running": worker_running,
            "drain_rate_per_sec": round(self._drain_rate, 4),
            "eta_seconds": round(eta_seconds, 1) if eta_seconds else None,
            "eta_human": _format_eta(eta_seconds) if eta_seconds else None,
            "alerts": alerts,
        }


def _format_eta(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f}h"


# ── Safe Mode ──

class SafeMode:
    """Tracks system reboots and enables safe mode if too many occur.

    Safe mode: skip all TeslaUSB services, keep SSH + AP available.
    Prevents an SD-card corruption death spiral.

    Usage:
        sm = SafeMode()
        if sm.is_safe_mode():
            # Skip heavy services, just run SSH + web
            ...
        sm.record_boot()  # Call on every normal boot
    """

    def __init__(self):
        self._safe_mode_active = False

    def is_safe_mode(self) -> bool:
        """Check if safe mode is currently active."""
        try:
            if SAFE_MODE_FILE.exists():
                content = SAFE_MODE_FILE.read_text().strip()
                return content.lower() in ("1", "true", "yes", "on")
        except OSError:
            pass
        return self._safe_mode_active

    def _get_system_uptime(self) -> float:
        """Get system uptime in seconds from /proc/uptime.
        Returns -1 on failure (non-Linux or permission denied).
        """
        try:
            with open("/proc/uptime", "r") as f:
                return float(f.read().split()[0])
        except (OSError, ValueError, IndexError):
            return -1.0

    def record_boot(self) -> None:
        """Record a boot event in the reboot tracker.

        Uses /proc/uptime to distinguish REAL system reboots from
        process restarts. If the current uptime is LOWER than the
        last recorded uptime, the system actually rebooted.
        """
        try:
            current_uptime = self._get_system_uptime()
            if current_uptime < 0:
                # Can't read uptime (non-Linux) — skip safe mode
                return

            REBOOT_TRACKER.parent.mkdir(parents=True, exist_ok=True)
            now = time.time()

            # Read existing records with their uptimes
            records: list[tuple[float, float]] = []  # (wall_time, uptime)
            if REBOOT_TRACKER.exists():
                for line in REBOOT_TRACKER.read_text().strip().split("\n"):
                    parts = line.strip().split(",")
                    if len(parts) == 2:
                        try:
                            records.append((float(parts[0]), float(parts[1])))
                        except ValueError:
                            pass

            # Check if this is a REAL reboot: current uptime < last recorded uptime
            is_real_reboot = True
            if records:
                last_wall, last_uptime = records[-1]
                # Same boot session: uptime increases monotonically
                # New boot: uptime resets to near-zero
                if current_uptime > last_uptime + 10:
                    # Uptime grew — same system, just process restart. Skip.
                    logger.debug("Process restart detected (uptime %.0f > %.0f) — not a reboot",
                                current_uptime, last_uptime)
                    # Still save this record so we know the last state
                    records.append((now, current_uptime))
                    if len(records) > 10:
                        records = records[-10:]
                    REBOOT_TRACKER.write_text(
                        "\n".join(f"{w},{u}" for w, u in records)
                    )
                    return
                elif current_uptime < last_uptime:
                    logger.info("System reboot detected (uptime %.0f < %.0f)",
                               current_uptime, last_uptime)
                    is_real_reboot = True

            # Record this actual boot
            records.append((now, current_uptime))

            # Filter to last N minutes
            window_start = now - (SAFE_MODE_WINDOW_MINUTES * 60)
            recent = [(w, u) for w, u in records if w >= window_start]
            recent.append((now, current_uptime))

            # Write back (keep last 20 entries for debugging)
            REBOOT_TRACKER.write_text(
                "\n".join(f"{w},{u}" for w, u in recent[-20:])
            )

            # Check threshold
            if is_real_reboot and len(recent) >= SAFE_MODE_REBOOT_COUNT:
                logger.error(
                    "%d reboots in %d minutes — ENTERING SAFE MODE",
                    len(recent), SAFE_MODE_WINDOW_MINUTES,
                )
                self.enable()

        except OSError:
            pass

    def enable(self) -> None:
        """Enable safe mode."""
        self._safe_mode_active = True
        try:
            SAFE_MODE_FILE.parent.mkdir(parents=True, exist_ok=True)
            SAFE_MODE_FILE.write_text("true")
        except OSError:
            pass

    def disable(self) -> None:
        """Disable safe mode after manual recovery."""
        self._safe_mode_active = False
        try:
            SAFE_MODE_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    def get_reboot_history(self) -> list[float]:
        """Get list of recent boot timestamps."""
        try:
            if REBOOT_TRACKER.exists():
                return [
                    float(line.strip())
                    for line in REBOOT_TRACKER.read_text().strip().split("\n")
                    if line.strip()
                ]
        except (OSError, ValueError):
            pass
        return []


# ── Application-wide singletons ──
hardware_watchdog = HardwareWatchdog()
archive_watchdog = ArchiveWatchdog()
safe_mode = SafeMode()
