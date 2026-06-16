#!/usr/bin/env bash
# ===========================================================================
# Tesla Journey OS — Present USB Gadget
#
# Switches the Pi into USB mass storage mode so the Tesla vehicle
# can access the dashcam, light show, and music partitions.
#
# Usage: sudo ./present_usb.sh [--boot]
#   --boot   Skip cleanup steps (nothing is mounted yet at boot)
# ===========================================================================
set -euo pipefail

APP_DIR="/opt/tesla-journey-os"
IMAGES_DIR="${APP_DIR}/data/images"
GADGET_NAME="tesla_journey"
GADGET_PATH="/sys/kernel/config/usb_gadget/${GADGET_NAME}"
RO_MOUNT_DIR="/mnt/tjos_gadget"
STATE_FILE="/var/run/tjos_usb_mode"
TARGET_USER="${SUDO_USER:-pi}"

IMG_CAM="${IMAGES_DIR}/usb_cam.img"
IMG_LS="${IMAGES_DIR}/usb_lightshow.img"
IMG_MUSIC="${IMAGES_DIR}/usb_music.img"

BOOT_MODE=0
[ "${1:-}" = "--boot" ] && BOOT_MODE=1

echo "=== TJOS — Present USB Gadget ==="

# Load required kernel modules (libcomposite creates the usb_gadget configfs dir)
modprobe libcomposite 2>/dev/null || true
modprobe dwc2 2>/dev/null || true

# Ensure configfs is mounted
if ! mountpoint -q /sys/kernel/config 2>/dev/null; then
    modprobe configfs 2>/dev/null || true
    modprobe libcomposite 2>/dev/null || true
    mount -t configfs none /sys/kernel/config 2>/dev/null || {
        echo "ERROR: Cannot mount configfs" >&2; exit 1;
    }
fi

# ── Unmount any existing RW mounts (skip at boot) ──
if [ "$BOOT_MODE" -eq 0 ]; then
    echo "Unmounting any existing mounts..."
    sync

    for mp in /mnt/gadget/part1 /mnt/gadget/part2 /mnt/gadget/part3 \
              "${RO_MOUNT_DIR}/part1-ro" "${RO_MOUNT_DIR}/part2-ro" "${RO_MOUNT_DIR}/part3-ro"; do
        if mountpoint -q "$mp" 2>/dev/null; then
            umount -lf "$mp" 2>/dev/null || true
            echo "  Unmounted $mp"
        fi
    done

    # Clean up loop devices
    for img in "$IMG_CAM" "$IMG_LS" "$IMG_MUSIC"; do
        [ -f "$img" ] || continue
        for loop in $(losetup -j "$img" 2>/dev/null | cut -d: -f1); do
            [ -n "$loop" ] && losetup -d "$loop" 2>/dev/null || true
        done
    done
    sync
fi

# ── Check images exist ──
for img in "$IMG_CAM" "$IMG_LS"; do
    [ -f "$img" ] || { echo "ERROR: Image not found: $img" >&2; exit 1; }
done

# ── Clean up old gadget ──
if [ -d "$GADGET_PATH" ]; then
    echo "Removing existing gadget..."
    [ -f "$GADGET_PATH/UDC" ] && echo "" > "$GADGET_PATH/UDC" 2>/dev/null || true
    sleep 0.3

    # Clear LUN files
    for lun in "$GADGET_PATH"/functions/mass_storage.usb0/lun.*; do
        [ -f "$lun/file" ] && echo "" > "$lun/file" 2>/dev/null || true
    done

    # Remove symlinks and directories
    rm -f "$GADGET_PATH"/configs/*/mass_storage.* 2>/dev/null || true
    rmdir "$GADGET_PATH"/configs/*/strings/* 2>/dev/null || true
    rmdir "$GADGET_PATH"/configs/* 2>/dev/null || true
    rmdir "$GADGET_PATH"/functions/mass_storage.usb0/lun.* 2>/dev/null || true
    rmdir "$GADGET_PATH"/functions/mass_storage.usb0 2>/dev/null || true
    rmdir "$GADGET_PATH"/functions/* 2>/dev/null || true
    rmdir "$GADGET_PATH"/strings/* 2>/dev/null || true
    rmdir "$GADGET_PATH" 2>/dev/null || true
    sleep 0.2
fi

# ── Create gadget ──
echo "Creating ConfigFS gadget..."
mkdir -p "$GADGET_PATH"

# Device descriptors
echo 0x1d6b > "$GADGET_PATH/idVendor"
echo 0x0104 > "$GADGET_PATH/idProduct"
echo 0x0100 > "$GADGET_PATH/bcdDevice"
echo 0x0200 > "$GADGET_PATH/bcdUSB"

# Strings
mkdir -p "$GADGET_PATH/strings/0x409"
echo "$(cat /proc/sys/kernel/random/uuid 2>/dev/null | cut -c1-15 || echo 'TJOS00001')" > "$GADGET_PATH/strings/0x409/serialnumber"
echo "Tesla Journey OS" > "$GADGET_PATH/strings/0x409/manufacturer"
echo "Tesla Storage" > "$GADGET_PATH/strings/0x409/product"

# Configuration
mkdir -p "$GADGET_PATH/configs/c.1/strings/0x409"
echo "TeslaCam + Media" > "$GADGET_PATH/configs/c.1/strings/0x409/configuration"
echo 500 > "$GADGET_PATH/configs/c.1/MaxPower"

# Mass storage function
mkdir -p "$GADGET_PATH/functions/mass_storage.usb0"
echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/stall"

# LUN 0: TeslaCam (RW)
mkdir -p "$GADGET_PATH/functions/mass_storage.usb0/lun.0"
echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/lun.0/removable"
echo 0 > "$GADGET_PATH/functions/mass_storage.usb0/lun.0/ro"
echo 0 > "$GADGET_PATH/functions/mass_storage.usb0/lun.0/cdrom"
echo "$IMG_CAM" > "$GADGET_PATH/functions/mass_storage.usb0/lun.0/file"

# LUN 1: LightShow (RO)
mkdir -p "$GADGET_PATH/functions/mass_storage.usb0/lun.1"
echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/lun.1/removable"
echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/lun.1/ro"
echo 0 > "$GADGET_PATH/functions/mass_storage.usb0/lun.1/cdrom"
echo "$IMG_LS" > "$GADGET_PATH/functions/mass_storage.usb0/lun.1/file"

# LUN 2: Music (RO) — optional
if [ -f "$IMG_MUSIC" ]; then
    mkdir -p "$GADGET_PATH/functions/mass_storage.usb0/lun.2"
    echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/lun.2/removable"
    echo 1 > "$GADGET_PATH/functions/mass_storage.usb0/lun.2/ro"
    echo 0 > "$GADGET_PATH/functions/mass_storage.usb0/lun.2/cdrom"
    echo "$IMG_MUSIC" > "$GADGET_PATH/functions/mass_storage.usb0/lun.2/file"
fi

# Link function to config
ln -sf "$GADGET_PATH/functions/mass_storage.usb0" "$GADGET_PATH/configs/c.1/"

# ── Find and bind UDC ──
echo "Finding UDC device..."
UDC=""
for i in $(seq 1 50); do
    UDC=$(ls /sys/class/udc 2>/dev/null | head -n1 || true)
    [ -n "$UDC" ] && break
    sleep 0.1
done

if [ -z "$UDC" ]; then
    echo "ERROR: No UDC device found. Is dwc2 loaded?" >&2
    exit 1
fi

echo "Binding to UDC: $UDC"
echo "$UDC" > "$GADGET_PATH/UDC"

# ── Local RO mounts (Pi can read TeslaCam footage) ──
echo "Mounting locally (read-only)..."
mkdir -p "$RO_MOUNT_DIR/part1-ro" "$RO_MOUNT_DIR/part2-ro" "${RO_MOUNT_DIR}/part3-ro"
UID_VAL=$(id -u "$TARGET_USER" 2>/dev/null || echo 1000)
GID_VAL=$(id -g "$TARGET_USER" 2>/dev/null || echo 1000)

# Mount TeslaCam
LOOP_CAM=$(losetup --show -f "$IMG_CAM" 2>/dev/null || true)
if [ -n "$LOOP_CAM" ]; then
    mount -t exfat -o ro,uid="$UID_VAL",gid="$GID_VAL",umask=022 "$LOOP_CAM" "$RO_MOUNT_DIR/part1-ro" 2>/dev/null || \
    mount -t vfat -o ro,uid="$UID_VAL",gid="$GID_VAL",umask=022 "$LOOP_CAM" "$RO_MOUNT_DIR/part1-ro" 2>/dev/null || \
    mount -o ro "$LOOP_CAM" "$RO_MOUNT_DIR/part1-ro" 2>/dev/null || true
    echo "  TeslaCam mounted at $RO_MOUNT_DIR/part1-ro"
fi

# Mount LightShow
LOOP_LS=$(losetup --show -f "$IMG_LS" 2>/dev/null || true)
if [ -n "$LOOP_LS" ]; then
    mount -t vfat -o ro,uid="$UID_VAL",gid="$GID_VAL",umask=022 "$LOOP_LS" "$RO_MOUNT_DIR/part2-ro" 2>/dev/null || \
    mount -o ro "$LOOP_LS" "$RO_MOUNT_DIR/part2-ro" 2>/dev/null || true
fi

# Mount Music
if [ -f "$IMG_MUSIC" ]; then
    LOOP_MUSIC=$(losetup --show -f "$IMG_MUSIC" 2>/dev/null || true)
    if [ -n "$LOOP_MUSIC" ]; then
        mount -t vfat -o ro,uid="$UID_VAL",gid="$GID_VAL",umask=022 "$LOOP_MUSIC" "$RO_MOUNT_DIR/part3-ro" 2>/dev/null || \
        mount -o ro "$LOOP_MUSIC" "$RO_MOUNT_DIR/part3-ro" 2>/dev/null || true
    fi
fi

# ── Write state ──
echo "present" > "$STATE_FILE" 2>/dev/null || true

echo ""
echo "=== USB Gadget Presented ==="
echo "  LUN0: TeslaCam (RW) ← car writes dashcam here"
echo "  LUN1: LightShow (RO) ← car reads light shows"
[ -f "$IMG_MUSIC" ] && echo "  LUN2: Music (RO) ← car reads music/chimes"
echo "  TeslaCam accessible at: $RO_MOUNT_DIR/part1-ro/TeslaCam"
echo ""
echo "Plug the Pi into your Tesla's USB port now."
