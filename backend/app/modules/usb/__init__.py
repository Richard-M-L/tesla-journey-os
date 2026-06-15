"""
USB Gadget Manager — presents the Pi as a multi-LUN USB mass storage device.

Ported from TeslaUSB. Uses Linux ConfigFS to create a USB gadget with:
  - LUN 0: TeslaCam (read-write)  — Tesla writes dashcam footage here
  - LUN 1: LightShow (read-only)  — Tesla reads custom light shows
  - LUN 2: Music (read-only)      — Tesla reads music, lock chimes, etc.

This module is Linux-specific. On non-Linux systems, all functions
return False/None gracefully.

Architecture:
  ┌──────────────────────────────────────────────────┐
  │  Raspberry Pi                                     │
  │  ┌─────────────┐  ┌──────────┐  ┌───────────┐   │
  │  │ usb_cam.img │  │ ls.img   │  │ music.img │   │
  │  │ (exFAT)     │  │ (FAT32)  │  │ (FAT32)   │   │
  │  └──────┬──────┘  └────┬─────┘  └─────┬─────┘   │
  │         │ loop0         │ loop1         │ loop2   │
  │         ▼               ▼               ▼         │
  │  ┌──────────────────────────────────────────────┐ │
  │  │  ConfigFS Gadget: /sys/kernel/config/usb_... │ │
  │  │  mass_storage.usb0                           │ │
  │  │  ├── lun.0/file → usb_cam.img    (RW)       │ │
  │  │  ├── lun.1/file → usb_ls.img     (RO)       │ │
  │  │  └── lun.2/file → usb_music.img  (RO)       │ │
  │  └──────────────────────┬───────────────────────┘ │
  │                         │ UDC: fe980000.usb       │
  └─────────────────────────┼─────────────────────────┘
                            │ USB cable
                     ┌──────▼──────┐
                     │  Tesla Car  │
                     └─────────────┘
"""

from app.modules.usb.gadget import UsbGadgetManager, usb_manager
from app.modules.usb.mode import detect_mode, current_mode, is_present, is_edit

__all__ = ["UsbGadgetManager", "usb_manager", "detect_mode", "current_mode", "is_present", "is_edit"]
