"""
ConfigFS USB Gadget Manager — Linux kernel ConfigFS interface.

Manages the lifecycle of a multi-LUN USB mass storage gadget:
  - setup(): Create gadget directories and configure LUNs
  - present(): Bind to UDC — car can access the drives
  - edit(): Unbind from UDC — Pi can modify drive contents
  - teardown(): Remove the gadget entirely

Ported from TeslaUSB's present_usb.sh and related service code.
"""

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("usb.gadget")

# ConfigFS paths
CONFIGFS_ROOT = Path("/sys/kernel/config")
GADGET_BASE = CONFIGFS_ROOT / "usb_gadget"
GADGET_NAME = "tesla_journey"
GADGET_PATH = GADGET_BASE / GADGET_NAME
UDC_PATH = Path("/sys/class/udc")

# State file
STATE_FILE = Path("/var/run/tjos_usb_mode")

# Default image locations (match config.yaml)
DEFAULT_IMAGES = {
    "cam": "/opt/tesla-journey-os/data/images/usb_cam.img",
    "lightshow": "/opt/tesla-journey-os/data/images/usb_lightshow.img",
    "music": "/opt/tesla-journey-os/data/images/usb_music.img",
}

# RO mount locations (where Pi reads files while gadget is active)
RO_MOUNT_DIR = Path("/mnt/tjos_gadget")


@dataclass
class LunConfig:
    """Configuration for a single LUN (Logical Unit Number)."""
    index: int
    image_path: str
    readonly: bool
    removable: bool = True
    cdrom: bool = False


class UsbGadgetManager:
    """Manages the Linux USB Gadget via ConfigFS.

    Usage:
        mgr = UsbGadgetManager()
        if mgr.is_supported():
            mgr.setup()
            mgr.present()  # Car can access drives
            # ... car writes dashcam footage ...
            mgr.edit()     # Stop gadget, Pi can modify
            mgr.teardown()
    """

    def __init__(self, images: dict[str, str] | None = None):
        self._images = images or DEFAULT_IMAGES
        self._luns = [
            LunConfig(0, self._images["cam"], readonly=False),
            LunConfig(1, self._images["lightshow"], readonly=True),
        ]
        if self._images.get("music") and os.path.exists(self._images["music"]):
            self._luns.append(LunConfig(2, self._images["music"], readonly=True))

    # ── Capability checks ──

    def is_supported(self) -> bool:
        """Check if this system supports USB gadget mode."""
        return (
            CONFIGFS_ROOT.exists()
            and GADGET_BASE.exists()
            and any(UDC_PATH.iterdir())
        )

    def _has_udc(self) -> bool:
        """Check if a USB Device Controller is available."""
        try:
            return bool(list(UDC_PATH.iterdir()))
        except OSError:
            return False

    def _get_udc(self) -> str | None:
        """Get the first available UDC device name."""
        try:
            udcs = list(UDC_PATH.iterdir())
            return udcs[0].name if udcs else None
        except OSError:
            return None

    def _ensure_configfs(self) -> bool:
        """Ensure configfs is mounted and required modules are loaded."""
        if not CONFIGFS_ROOT.exists():
            return False

        # Check if configfs is mounted
        try:
            result = subprocess.run(
                ["mountpoint", "-q", str(CONFIGFS_ROOT)],
                capture_output=True, timeout=5,
            )
            if result.returncode != 0:
                subprocess.run(["modprobe", "configfs"], capture_output=True, timeout=5)
                subprocess.run(["modprobe", "libcomposite"], capture_output=True, timeout=5)
                subprocess.run(
                    ["mount", "-t", "configfs", "none", str(CONFIGFS_ROOT)],
                    capture_output=True, timeout=5,
                )
            return True
        except Exception:
            logger.exception("Failed to ensure configfs")
            return False

    # ── Mode detection ──

    def is_active(self) -> bool:
        """Check if the gadget is currently active (present mode)."""
        try:
            # Check if our gadget exists and is bound to a UDC
            udc_file = GADGET_PATH / "UDC"
            if not udc_file.exists():
                return False
            content = udc_file.read_text().strip()
            return bool(content)
        except OSError:
            return False

    def is_present_mode(self) -> bool:
        """Check if the system is in present mode (gadget active, Tesla can access)."""
        return self.is_active()

    def is_edit_mode(self) -> bool:
        """Check if the system is in edit mode (gadget stopped, Pi can modify)."""
        # Edit mode = gadget not active, but our directory exists
        return (not self.is_active()) and GADGET_PATH.exists()

    # ── State file ──

    def _write_state(self, mode: str) -> None:
        """Write the current mode to the state file."""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(mode)
        except OSError:
            pass

    def read_state(self) -> str:
        """Read the current mode from the state file."""
        try:
            return STATE_FILE.read_text().strip().lower()
        except (OSError, FileNotFoundError):
            return "unknown"

    # ── Gadget lifecycle ──

    def setup(self) -> bool:
        """Create the ConfigFS gadget with all LUNs.

        This writes the directory structure under
        /sys/kernel/config/usb_gadget/tesla_journey/.
        Must be run as root (or with sudo).
        """
        if not self._ensure_configfs():
            logger.error("configfs not available")
            return False

        try:
            # ── 1. Clean up any existing gadget ──
            self.teardown()

            # ── 2. Create gadget directory ──
            GADGET_PATH.mkdir(parents=True, exist_ok=True)

            # ── 3. Device descriptors ──
            self._write_gadget_attr("idVendor", "0x1d6b")
            self._write_gadget_attr("idProduct", "0x0104")
            self._write_gadget_attr("bcdDevice", "0x0100")
            self._write_gadget_attr("bcdUSB", "0x0200")

            # ── 4. String descriptors ──
            strings_dir = GADGET_PATH / "strings" / "0x409"
            strings_dir.mkdir(parents=True, exist_ok=True)
            serial = self._generate_serial()
            (strings_dir / "serialnumber").write_text(serial)
            (strings_dir / "manufacturer").write_text("Tesla Journey OS")
            (strings_dir / "product").write_text("Tesla Storage")

            # ── 5. Configuration ──
            config_dir = GADGET_PATH / "configs" / "c.1"
            config_str_dir = config_dir / "strings" / "0x409"
            config_str_dir.mkdir(parents=True, exist_ok=True)
            (config_str_dir / "configuration").write_text("TeslaCam + Media")
            (config_dir / "MaxPower").write_text("500")

            # ── 6. Mass storage function with LUNs ──
            func_dir = GADGET_PATH / "functions" / "mass_storage.usb0"
            func_dir.mkdir(parents=True, exist_ok=True)

            # Set stall for compatibility
            (func_dir / "stall").write_text("1")

            for lun in self._luns:
                lun_dir = func_dir / f"lun.{lun.index}"
                lun_dir.mkdir(parents=True, exist_ok=True)

                # Verify image exists
                if not os.path.exists(lun.image_path):
                    logger.warning("LUN %d image not found: %s", lun.index, lun.image_path)
                    continue

                (lun_dir / "removable").write_text("1" if lun.removable else "0")
                (lun_dir / "ro").write_text("1" if lun.readonly else "0")
                (lun_dir / "cdrom").write_text("1" if lun.cdrom else "0")
                (lun_dir / "file").write_text(lun.image_path)

            # ── 7. Link function to configuration ──
            link_path = config_dir / "mass_storage.usb0"
            if not link_path.exists():
                os.symlink(str(func_dir), str(link_path))

            logger.info("Gadget setup complete: %d LUNs", len(self._luns))
            self._write_state("edit")
            return True

        except OSError as e:
            logger.error("Gadget setup failed: %s", e)
            return False

    def present(self) -> bool:
        """Present the USB gadget to the car (bind to UDC).

        This makes the Pi appear as USB storage devices when plugged
        into the Tesla's USB port. The car can then:
          - Write dashcam footage to LUN 0 (TeslaCam)
          - Read light shows from LUN 1 (LightShow)
          - Read music from LUN 2 (Music)

        Returns True if successful.
        """
        if not self._ensure_configfs():
            return False

        try:
            udc = self._get_udc()
            if not udc:
                logger.error("No UDC device found — is dwc2 module loaded?")
                return False

            # Bind to UDC
            (GADGET_PATH / "UDC").write_text(udc)
            logger.info("Gadget bound to UDC: %s", udc)

            # Mount images locally in read-only mode for Pi access
            self._mount_local_ro()

            self._write_state("present")
            return True

        except OSError as e:
            logger.error("Failed to present gadget: %s", e)
            return False

    def edit(self) -> bool:
        """Switch to edit mode — unbind from UDC, stop the gadget.

        The Pi can now modify the backing disk images (add light shows,
        music, lock chimes, etc.). The car cannot access the drives.
        """
        try:
            # ── 1. Unmount local RO mounts ──
            self._unmount_local_ro()

            # ── 2. Unbind from UDC ──
            udc_file = GADGET_PATH / "UDC"
            if udc_file.exists():
                udc_file.write_text("")  # Empty = unbind
                time.sleep(0.3)

            logger.info("Gadget unbound — edit mode")
            self._write_state("edit")
            return True

        except OSError as e:
            logger.error("Failed to switch to edit mode: %s", e)
            return False

    def teardown(self) -> bool:
        """Completely remove the gadget configuration.

        Unbinds from UDC, clears LUN files, removes all directories.
        Safe to call even if gadget doesn't exist.
        """
        try:
            if not GADGET_PATH.exists():
                return True

            # ── 1. Unmount local RO mounts ──
            self._unmount_local_ro()

            # ── 2. Unbind UDC ──
            udc_file = GADGET_PATH / "UDC"
            if udc_file.exists():
                try:
                    udc_file.write_text("")
                except OSError:
                    pass
                time.sleep(0.3)

            # ── 3. Clear LUN backing files (releases kernel refs) ──
            func_dir = GADGET_PATH / "functions" / "mass_storage.usb0"
            for lun_dir in sorted(func_dir.glob("lun.*")):
                lun_file = lun_dir / "file"
                if lun_file.exists():
                    try:
                        lun_file.write_text("")
                    except OSError:
                        pass
            time.sleep(0.1)

            # ── 4. Remove config symlink ──
            for config_dir in sorted((GADGET_PATH / "configs").glob("c.*")):
                link = config_dir / "mass_storage.usb0"
                if link.is_symlink():
                    link.unlink()

            # ── 5. Remove all directories (deepest first) ──
            for root, dirs, files in os.walk(str(GADGET_PATH), topdown=False):
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except OSError:
                        pass

            # ── 6. Try to remove the top-level gadget dir ──
            try:
                GADGET_PATH.rmdir()
            except OSError:
                # May fail if kernel still holds references — force cleanup
                pass

            logger.info("Gadget teardown complete")
            self._write_state("unknown")
            return True

        except OSError:
            logger.exception("Gadget teardown failed")
            return False

    # ── Local mount helpers (read-only access for Pi) ──

    def _mount_local_ro(self) -> None:
        """Mount images locally in read-only mode so the Pi can read files.

        The Tesla writes to LUN 0 (TeslaCam) — the Pi reads from the
        mount to index new dashcam videos.
        """
        RO_MOUNT_DIR.mkdir(parents=True, exist_ok=True)

        for lun in self._luns:
            mp = RO_MOUNT_DIR / f"part{lun.index + 1}-ro"
            mp.mkdir(parents=True, exist_ok=True)

            # Create loop device
            try:
                result = subprocess.run(
                    ["losetup", "--show", "-f", lun.image_path],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    logger.warning("Failed to create loop for %s", lun.image_path)
                    continue
                loop_dev = result.stdout.strip()
            except Exception:
                continue

            # Detect FS type and mount
            try:
                blkid = subprocess.run(
                    ["blkid", "-o", "value", "-s", "TYPE", loop_dev],
                    capture_output=True, text=True, timeout=5,
                )
                fs_type = blkid.stdout.strip() or "vfat"

                mount_cmd = [
                    "nsenter", "--mount=/proc/1/ns/mnt",
                    "mount", "-t", fs_type, "-o", "ro",
                    loop_dev, str(mp),
                ]
                subprocess.run(mount_cmd, check=True, capture_output=True, timeout=10)
                logger.debug("Mounted %s at %s", lun.image_path, mp)
            except subprocess.CalledProcessError as e:
                logger.warning("Failed to mount %s: %s", lun.image_path, e)

    def _unmount_local_ro(self) -> None:
        """Unmount all local read-only mounts."""
        for mp_dir in sorted(RO_MOUNT_DIR.glob("part*-ro")):
            try:
                subprocess.run(["umount", "-lf", str(mp_dir)],
                             capture_output=True, timeout=10)
            except Exception:
                pass

    # ── Helpers ──

    def _write_gadget_attr(self, name: str, value: str) -> None:
        """Write a value to a gadget attribute file."""
        (GADGET_PATH / name).write_text(value)

    def _generate_serial(self) -> str:
        """Generate a unique serial number for USB descriptors."""
        try:
            import uuid
            return str(uuid.uuid4())[:15]
        except Exception:
            return "TJOS00000000001"

    def get_status(self) -> dict:
        """Return USB gadget status for the API/frontend."""
        mode = self.read_state()
        active = self.is_active()

        lun_info = []
        for lun in self._luns:
            img = Path(lun.image_path)
            lun_info.append({
                "index": lun.index,
                "name": ["TeslaCam", "LightShow", "Music"][lun.index] if lun.index < 3 else f"LUN{lun.index}",
                "readonly": lun.readonly,
                "image_path": str(img),
                "image_exists": img.exists(),
                "image_size_mb": round(img.stat().st_size / (1024 * 1024), 1) if img.exists() else 0,
            })

        return {
            "supported": self.is_supported(),
            "mode": mode,
            "active": active,
            "udc_available": self._has_udc(),
            "udc_device": self._get_udc(),
            "luns": lun_info,
            "gadget_path": str(GADGET_PATH) if GADGET_PATH.exists() else None,
        }


# Singleton instance
usb_manager = UsbGadgetManager()
