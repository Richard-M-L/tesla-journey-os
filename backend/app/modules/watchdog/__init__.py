"""
System watchdog — safe mode detection and hardware watchdog timer.

Safe mode: tracks boot count to detect crash loops. If too many reboots
occur in a short window, heavy services are disabled so the admin can
access the web UI to fix configuration.

Hardware watchdog: pings the kernel watchdog device to reboot the Pi
if the application hangs.
"""

import logging
import os
import time

logger = logging.getLogger("watchdog")

SAFE_MODE_FILE = "/var/run/tjos_safe_mode"
MAX_BOOTS_IN_WINDOW = 3
BOOT_WINDOW_SECONDS = 300  # 5 minutes


class SafeMode:
    def record_boot(self) -> None:
        """Record this boot timestamp. Creates/updates the boot counter."""
        try:
            if os.path.exists(SAFE_MODE_FILE):
                with open(SAFE_MODE_FILE, "r") as f:
                    lines = f.read().strip().split("\n") if f.read().strip() else []
                # Re-read after checking existence
                with open(SAFE_MODE_FILE, "r") as f:
                    raw = f.read().strip()
                    lines = raw.split("\n") if raw else []
            else:
                lines = []

            now = time.time()
            # Prune old entries outside the window
            recent = [float(t) for t in lines if t and now - float(t) < BOOT_WINDOW_SECONDS]
            recent.append(now)

            os.makedirs(os.path.dirname(SAFE_MODE_FILE), exist_ok=True)
            with open(SAFE_MODE_FILE, "w") as f:
                f.write("\n".join(str(t) for t in recent))

            if len(recent) >= MAX_BOOTS_IN_WINDOW:
                logger.warning("Safe mode threshold reached: %d boots in %ds", len(recent), BOOT_WINDOW_SECONDS)
        except OSError:
            logger.debug("Cannot write safe mode file (read-only filesystem?)")

    def is_safe_mode(self) -> bool:
        """Check if the system should run in safe mode (reduced services)."""
        try:
            if not os.path.exists(SAFE_MODE_FILE):
                return False
            with open(SAFE_MODE_FILE, "r") as f:
                raw = f.read().strip()
                if not raw:
                    return False
                lines = raw.split("\n")
                now = time.time()
                recent = [float(t) for t in lines if t and now - float(t) < BOOT_WINDOW_SECONDS]
                return len(recent) >= MAX_BOOTS_IN_WINDOW
        except OSError:
            return False


class HardwareWatchdog:
    """Pings the Linux kernel watchdog device (/dev/watchdog)."""

    def __init__(self):
        self._running = False
        self._watchdog_fd = None

    def start(self) -> None:
        try:
            self._watchdog_fd = os.open("/dev/watchdog", os.O_WRONLY)
            self._running = True
            logger.info("Hardware watchdog started")
        except OSError:
            logger.debug("No /dev/watchdog device — skipping hardware watchdog")

    def stop(self) -> None:
        self._running = False
        if self._watchdog_fd is not None:
            try:
                # Write magic character 'V' to stop the watchdog gracefully
                os.write(self._watchdog_fd, b"V")
                os.close(self._watchdog_fd)
            except OSError:
                pass
            self._watchdog_fd = None


class ArchiveWatchdog:
    """Monitors archive queue health."""

    def check(self, queue_depth: int = 0, worker_running: bool = True) -> dict:
        healthy = worker_running and queue_depth < 1000
        return {
            "healthy": healthy,
            "queue_depth": queue_depth,
            "worker_running": worker_running,
        }


safe_mode = SafeMode()
hardware_watchdog = HardwareWatchdog()
archive_watchdog = ArchiveWatchdog()
