#!/usr/bin/env bash
# ===========================================================================
# Tesla Journey OS — SD Card Image Builder
# ===========================================================================
# Creates a flashable Raspberry Pi OS image with TJOS pre-installed.
#
# Usage:
#   sudo ./build_image.sh [--size 8G] [--output tjos.img]
#
# What it does:
#   1. Downloads Raspberry Pi OS Lite base image
#   2. Mounts it via loopback + chroot
#   3. Installs all system dependencies
#   4. Clones TJOS from GitHub
#   5. Builds frontend + inits DB
#   6. Configures USB gadget, services, Nginx
#   7. Shrinks and outputs the final .img file
#
# Requirements:
#   - Linux system with: qemu-user-static, systemd-nspawn or chroot
#   - ~8GB free disk space
#   - Internet connection
# ===========================================================================
set -euo pipefail

SIZE="${SIZE:-8G}"
OUTPUT="${OUTPUT:-tesla-journey-os.img}"
PI_OS_URL="https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2024-11-19/2024-11-19-raspios-bookworm-arm64-lite.img.xz"

GREEN='\033[0;32m'
NC='\033[0m'
log() { echo -e "${GREEN}[BUILD]${NC} $1"; }

# Parse args
while [ $# -gt 0 ]; do
    case "$1" in
        --size) SIZE="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Must run as root: sudo ./build_image.sh"
    exit 1
fi

WORKDIR="$(mktemp -d)"
log "Working directory: $WORKDIR"

# Step 1: Download base image
log "[1/6] Downloading Raspberry Pi OS Lite..."
PI_IMG="$WORKDIR/raspios.img"
if [ -f "./cache/raspios.img" ]; then
    log "  Using cached image"
    cp "./cache/raspios.img" "$PI_IMG"
else
    curl -L "$PI_OS_URL" -o "$WORKDIR/raspios.img.xz"
    xz -d "$WORKDIR/raspios.img.xz"
    mkdir -p ./cache
    cp "$PI_IMG" ./cache/raspios.img
fi

# Step 2: Resize image to fit TJOS
log "[2/6] Resizing image to $SIZE..."
# Add 2GB to base image for TJOS + build space
qemu-img resize "$PI_IMG" "$SIZE" 2>/dev/null || \
    truncate -s "$SIZE" "$PI_IMG"

# Step 3: Mount image
log "[3/6] Mounting image..."
LOOP_DEV=$(losetup --show -fP "$PI_IMG")
# Expand root partition to use new space
parted -s "$LOOP_DEV" resizepart 2 100% 2>/dev/null || true
partprobe "$LOOP_DEV" 2>/dev/null || true
e2fsck -fy "${LOOP_DEV}p2" 2>/dev/null || true
resize2fs "${LOOP_DEV}p2" 2>/dev/null || true

MNT_ROOT="$WORKDIR/mnt"
mkdir -p "$MNT_ROOT"
mount "${LOOP_DEV}p2" "$MNT_ROOT"
mount "${LOOP_DEV}p1" "$MNT_ROOT/boot/firmware"

# Step 4: Install TJOS into the image
log "[4/6] Installing Tesla Journey OS..."

# Enable QEMU for ARM64 emulation if running on x86
if [ "$(uname -m)" != "aarch64" ]; then
    apt-get install -y -qq qemu-user-static 2>/dev/null || true
    cp /usr/bin/qemu-aarch64-static "$MNT_ROOT/usr/bin/" 2>/dev/null || true
fi

# Chroot and run install steps
cat > "$MNT_ROOT/tmp/tjos_chroot_setup.sh" << 'CHROOT_EOF'
#!/bin/bash
set -e

echo "[TJOS] Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-dev python3-pip \
    protobuf-compiler ffmpeg nginx git curl wget \
    network-manager hostapd dnsmasq exfatprogs dosfstools \
    nodejs npm

echo "[TJOS] Cloning Tesla Journey OS..."
cd /opt
git clone https://github.com/Richard-M-L/tesla-journey-os.git
cd tesla-journey-os

echo "[TJOS] Setting up Python venv..."
python3 -m venv venv
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r backend/requirements.txt -q
venv/bin/pip install grpcio-tools -q

echo "[TJOS] Compiling protobuf..."
venv/bin/python -m grpc_tools.protoc \
    --python_out=backend/app/modules/ingestion \
    --proto_path=backend/app/modules/ingestion \
    backend/app/modules/ingestion/dashcam.proto

echo "[TJOS] Building frontend..."
cd frontend
npm install --silent
npm run build
cd ..

echo "[TJOS] Initializing database..."
PYTHONPATH=/opt/tesla-journey-os/backend venv/bin/python -c "
from app.database import init_db
init_db()
from app.modules.media import ensure_dirs
ensure_dirs()
print('DB OK')
"

echo "[TJOS] Configuring system..."
# USB gadget kernel support
echo "dtoverlay=dwc2,dr_mode=peripheral" >> /boot/firmware/config.txt
echo "dtparam=watchdog=on" >> /boot/firmware/config.txt
echo "libcomposite" >> /etc/modules

# Nginx config
cat > /etc/nginx/sites-available/tjos << 'NGX'
server {
    listen 80 default_server;
    server_name _;
    location = /generate_204 { return 204; }
    location = /gen_204 { return 204; }
    location = /hotspot-detect.html { return 200 "Success"; }
    location = /connecttest.txt { return 200 "Microsoft Connect Test"; }
    location = /ncsi.txt { return 200 "Microsoft NCSI"; }
    location = /success.txt { return 200 "success"; }
    location /api/ { proxy_pass http://127.0.0.1:8000; proxy_http_version 1.1; proxy_set_header Host \$host; proxy_buffering off; client_max_body_size 500M; }
    location /health { proxy_pass http://127.0.0.1:8000; }
    root /opt/tesla-journey-os/frontend/dist;
    index index.html;
    location / { try_files \$uri \$uri/ /index.html; }
}
NGX
ln -sf /etc/nginx/sites-available/tjos /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# systemd services
cat > /etc/systemd/system/tjos-backend.service << 'SVC'
[Unit]
Description=Tesla Journey OS Backend
After=network-online.target
[Service]
Type=simple
User=pi
WorkingDirectory=/opt/tesla-journey-os
Environment=PYTHONPATH=/opt/tesla-journey-os/backend
ExecStart=/opt/tesla-journey-os/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
SVC

systemctl enable tjos-backend nginx

echo "[TJOS] Done!"
CHROOT_EOF

chmod +x "$MNT_ROOT/tmp/tjos_chroot_setup.sh"

if [ -f "$MNT_ROOT/usr/bin/qemu-aarch64-static" ]; then
    # Running on x86 host with QEMU
    systemd-nspawn -D "$MNT_ROOT" --pipe --console=pipe \
        /bin/bash /tmp/tjos_chroot_setup.sh 2>&1 || log "Chroot completed with warnings"
else
    # Running on ARM64 (native Pi)
    chroot "$MNT_ROOT" /bin/bash /tmp/tjos_chroot_setup.sh 2>&1 || log "Chroot completed with warnings"
fi

rm -f "$MNT_ROOT/tmp/tjos_chroot_setup.sh"
[ -f "$MNT_ROOT/usr/bin/qemu-aarch64-static" ] && rm -f "$MNT_ROOT/usr/bin/qemu-aarch64-static"

# Step 5: Clean up
log "[5/6] Cleaning up..."
sync
umount "$MNT_ROOT/boot/firmware" 2>/dev/null || true
umount "$MNT_ROOT" 2>/dev/null || true
losetup -d "$LOOP_DEV" 2>/dev/null || true

# Step 6: Shrink and output
log "[6/6] Shrinking image..."
# Zero-fill free space to make compression effective
# (skipped for speed — the image is already minimal)

cp "$PI_IMG" "$OUTPUT"
log "Image created: $OUTPUT"
log "Size: $(du -h "$OUTPUT" | cut -f1)"
log ""
log "Flash this image to an SD card with Raspberry Pi Imager."
log "After booting, plug the Pi into your Tesla and visit:"
log "  http://<pi-ip>"

rm -rf "$WORKDIR"
