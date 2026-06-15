#!/usr/bin/env bash
# ===========================================================================
# Tesla Journey OS — Edit Mode (unbind USB gadget)
#
# Stops the USB gadget so the Pi can modify the backing disk images
# (add light shows, music, lock chimes, etc.). The Tesla cannot
# access the drives in this mode.
#
# Usage: sudo ./edit_usb.sh
# ===========================================================================
set -euo pipefail

APP_DIR="/opt/tesla-journey-os"
IMAGES_DIR="${APP_DIR}/data/images"
GADGET_NAME="tesla_journey"
GADGET_PATH="/sys/kernel/config/usb_gadget/${GADGET_NAME}"
RO_MOUNT_DIR="/mnt/tjos_gadget"
STATE_FILE="/var/run/tjos_usb_mode"

echo "=== TJOS — Edit Mode ==="

# ── Unmount RO mounts ──
echo "Unmounting read-only mounts..."
sync
for mp in "$RO_MOUNT_DIR/part1-ro" "$RO_MOUNT_DIR/part2-ro" "$RO_MOUNT_DIR/part3-ro"; do
    if mountpoint -q "$mp" 2>/dev/null; then
        umount -lf "$mp" 2>/dev/null && echo "  Unmounted $mp" || echo "  Failed to unmount $mp (forcing...)" && umount -lf "$mp" 2>/dev/null || true
    fi
done

# ── Unbind UDC ──
if [ -f "$GADGET_PATH/UDC" ]; then
    echo "Unbinding from UDC..."
    echo "" > "$GADGET_PATH/UDC" 2>/dev/null || true
    sleep 0.5
    echo "  Unbound"
fi

# ── Clear LUN files (releases kernel references) ──
for lun in "$GADGET_PATH"/functions/mass_storage.usb0/lun.* 2>/dev/null; do
    [ -f "$lun/file" ] && echo "" > "$lun/file" 2>/dev/null || true
done
sleep 0.2

# ── Clean up loop devices ──
echo "Detaching loop devices..."
for img in "$IMAGES_DIR"/*.img; do
    [ -f "$img" ] || continue
    for loop in $(losetup -j "$img" 2>/dev/null | cut -d: -f1); do
        [ -n "$loop" ] && losetup -d "$loop" 2>/dev/null && echo "  Detached $loop" || true
    done
done
sync

# ── Write state ──
echo "edit" > "$STATE_FILE" 2>/dev/null || true

echo ""
echo "=== Edit Mode ==="
echo "  USB gadget is stopped. You can now:"
echo "    - Add/remove light show files"
echo "    - Update lock chimes and music"
echo "    - Modify disk images safely"
echo ""
echo "  To return to Present mode:"
echo "    sudo /opt/tesla-journey-os/deploy/present_usb.sh"
echo ""
echo "  Or via the web UI:"
echo "    Settings → USB → Present"
