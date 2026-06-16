#!/usr/bin/env bash
# ===========================================================================
# Tesla Journey OS — One-Click Raspberry Pi Install Script
# ===========================================================================
# Usage:
#   curl -sSL https://.../install.sh | sudo bash
#   or
#   chmod +x install.sh && sudo ./install.sh
#
# What this does:
#   1.  System deps (Python, Node, protoc, ffmpeg, nginx, nmcli, hostapd...)
#   2.  USB Gadget kernel setup (dwc2 overlay)
#   3.  Python venv + pip install
#   4.  Protobuf compile
#   5.  Frontend build (React → static files)
#   6.  Database init
#   7.  USB disk images (create + format)
#   8.  Nginx config (serve frontend, proxy API)
#   9.  systemd services (backend, wifi-monitor, boot-present)
#  10.  Captive portal dnsmasq redirect
#  11.  First-time mode: present USB gadget
#
# After install:
#   http://<pi-ip>         → TJOS Dashboard
#   http://<pi-ip>:8000    → Backend API directly
#   WiFi hotspot: "Tesla Journey OS" (no password by default)
# ===========================================================================

set -euo pipefail

# ── Config ──────────────────────────────────────────
APP_DIR="/opt/tesla-journey-os"
DATA_DIR="${APP_DIR}/data"
IMAGES_DIR="${DATA_DIR}/images"
VENV_DIR="${APP_DIR}/venv"
TARGET_USER="${SUDO_USER:-pi}"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[TJOS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Must be root
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root. Use: sudo ./install.sh"
fi

# Must be on a Pi (check for /proc/device-tree/model)
if ! grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
    warn "Not running on a Raspberry Pi? Some features (USB gadget) won't work."
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║    Tesla Journey OS — Pi Installer            ║"
echo "║    树莓派车载固件                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# If running from curl (no local repo), clone first
if [ ! -f "$APP_DIR/deploy/install.sh" ]; then
    log "Cloning Tesla Journey OS from GitHub..."
    apt-get install -y -qq -o Acquire::Retries=5 git 2>/dev/null || true
    mkdir -p /opt
    if [ -d "$APP_DIR" ]; then
        warn "$APP_DIR already exists, updating..."
        cd "$APP_DIR" && (git pull origin master 2>/dev/null || true)
    else
        # Retry clone up to 3 times
        for i in 1 2 3; do
            git clone https://github.com/Richard-M-L/tesla-journey-os.git "$APP_DIR" 2>/dev/null && break
            log "  git clone retry $i/3..."
            sleep 5
        done
    fi
    if [ ! -f "$APP_DIR/deploy/install.sh" ]; then
        err "Git clone 失败，请检查网络: https://github.com/Richard-M-L/tesla-journey-os.git"
    fi
    log "Repo ready at $APP_DIR"
fi

# ── Step 1: System Dependencies ──
log "[1/11] Installing system packages..."
# Retry apt operations — Pi Zero 2 W on WiFi can be flaky
for i in 1 2 3; do
    apt-get update -qq -o Acquire::Retries=5 && break
    log "  apt update retry $i/3..."
    sleep 5
done
apt-get install -y -qq -o Acquire::Retries=5 \
    python3 python3-venv python3-dev python3-pip \
    protobuf-compiler \
    ffmpeg \
    nginx \
    git curl wget \
    network-manager \
    hostapd dnsmasq \
    exfatprogs dosfstools \
    || err "apt-get install 失败，请检查网络连接"

# Node.js (for frontend build)
if ! command -v node &>/dev/null; then
    log "  Installing Node.js 22.x..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y -qq nodejs || warn "Node.js install failed — frontend won't build"
fi

log "  System packages installed."

# ── Step 2: USB Gadget Kernel Support ──
log "[2/11] Enabling USB Gadget kernel support (dwc2)..."
CONFIG_FILE="/boot/firmware/config.txt"
if [ -f "$CONFIG_FILE" ]; then
    # dwc2 for USB gadget
    if ! grep -q "dtoverlay=dwc2" "$CONFIG_FILE" 2>/dev/null; then
        echo "dtoverlay=dwc2" >> "$CONFIG_FILE"
        log "  dwc2 overlay added to config.txt"
    else
        log "  dwc2 overlay already enabled"
    fi
    # Hardware watchdog
    if ! grep -q "dtparam=watchdog=on" "$CONFIG_FILE" 2>/dev/null; then
        echo "dtparam=watchdog=on" >> "$CONFIG_FILE"
        log "  Hardware watchdog enabled in config.txt"
    else
        log "  Hardware watchdog already enabled"
    fi
else
    warn "  Could not find /boot/firmware/config.txt — USB gadget may not work"
fi

# Load dwc2 module now
modprobe dwc2 2>/dev/null || warn "  dwc2 module not available now (will load after reboot)"
modprobe libcomposite 2>/dev/null || true

# ── Step 3: Create Directory Structure ──
log "[3/11] Creating directory structure..."
mkdir -p "$DATA_DIR" "$IMAGES_DIR" \
         "$DATA_DIR/teslacam" "$DATA_DIR/archived" \
         "$DATA_DIR/media/LockChimes" "$DATA_DIR/media/LightShow" \
         "$DATA_DIR/media/Music" "$DATA_DIR/media/Boombox" \
         "$DATA_DIR/media/Wraps" "$DATA_DIR/media/LicensePlates"

chown -R "$TARGET_USER:$TARGET_USER" "$APP_DIR" 2>/dev/null || true

# ── Step 4: Python Virtual Environment ──
log "[4/11] Setting up Python environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi

# Pip base args: long timeout + retries for slow/unstable connections
PIP_ARGS="--default-timeout=120 --retries 5"
# Auto-detect Chinese network → use Tsinghua mirror
if ping -c 1 -W 2 pypi.tuna.tsinghua.edu.cn &>/dev/null; then
    PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn"
    log "  使用清华 PyPI 镜像"
elif ping -c 1 -W 2 mirrors.aliyun.com &>/dev/null; then
    PIP_MIRROR="-i https://mirrors.aliyun.com/pypi/simple --trusted-host mirrors.aliyun.com"
    log "  使用阿里云 PyPI 镜像"
else
    PIP_MIRROR=""
fi

"$VENV_DIR/bin/pip" install --upgrade pip $PIP_ARGS $PIP_MIRROR

if [ -f "$APP_DIR/backend/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/backend/requirements.txt" $PIP_ARGS $PIP_MIRROR
else
    "$VENV_DIR/bin/pip" install fastapi uvicorn sqlalchemy apscheduler pyyaml pydantic python-multipart watchfiles protobuf httpx $PIP_ARGS $PIP_MIRROR
fi

# Also install grpcio-tools for protobuf compilation
"$VENV_DIR/bin/pip" install grpcio-tools $PIP_ARGS $PIP_MIRROR 2>/dev/null || true

log "  Python venv ready."

# ── Step 5: Protobuf Compilation ──
log "[5/11] Compiling dashcam.proto..."
PROTO_DIR="$APP_DIR/backend/app/modules/ingestion"
if [ -f "$PROTO_DIR/dashcam.proto" ]; then
    protoc --python_out="$PROTO_DIR" --proto_path="$PROTO_DIR" "$PROTO_DIR/dashcam.proto"
    log "  dashcam_pb2.py compiled"
else
    warn "  dashcam.proto not found — parser will auto-compile at runtime"
fi

# ── Step 6: Frontend Build ──
log "[6/11] Building frontend..."
if command -v node &>/dev/null && [ -f "$APP_DIR/frontend/package.json" ]; then
    cd "$APP_DIR/frontend"
    npm install --silent 2>/dev/null || warn "  npm install had warnings"
    npm run build 2>/dev/null || warn "  Frontend build failed — serving API only"
    log "  Frontend built to frontend/dist/"
else
    warn "  Skipping frontend build (Node.js or package.json missing)"
fi

# ── Step 7: Database Initialization ──
log "[7/11] Initializing database..."
cd "$APP_DIR"
PYTHONPATH="$APP_DIR/backend" "$VENV_DIR/bin/python" -c "
from app.database import init_db
init_db()
from app.modules.media import ensure_dirs
ensure_dirs()
print('  Database initialized')
" || warn "  DB init failed — will retry on first startup"

# ── Step 8: USB Disk Images ──
log "[8/11] Creating USB gadget disk images..."

# ── Smart size detection ──
# Check available space on the data partition
AVAIL_GB=$(df -BG "$DATA_DIR" 2>/dev/null | tail -1 | awk '{print $4}' | sed 's/G//' || echo "0")
AVAIL_GB=${AVAIL_GB:-0}
log "  Available space: ~${AVAIL_GB} GB"

# Default sizes — adjusted based on available space
if [ "$AVAIL_GB" -lt 16 ] 2>/dev/null; then
    err "Not enough free space (${AVAIL_GB} GB). Need at least 16 GB for disk images."
fi

# Calculate suggested sizes: TeslaCam gets ~60% of available, LightShow 5%, Music 25%, reserve 10%
SUGG_CAM=$(( AVAIL_GB * 60 / 100 ))
SUGG_LS=2
SUGG_MUSIC=$(( AVAIL_GB * 25 / 100 ))
# Clamp to reasonable ranges
[ "$SUGG_CAM" -gt 128 ] && SUGG_CAM=128
[ "$SUGG_CAM" -lt 8 ] && SUGG_CAM=8
[ "$SUGG_MUSIC" -gt 64 ] && SUGG_MUSIC=64
[ "$SUGG_MUSIC" -lt 2 ] && SUGG_MUSIC=2

# Accept custom sizes from: command-line args, env vars, or interactive prompt
CAM_SIZE="${1:-${TJOS_CAM_SIZE:-}}"
LS_SIZE="${2:-${TJOS_LS_SIZE:-}}"
MUSIC_SIZE="${3:-${TJOS_MUSIC_SIZE:-}}"

# Interactive mode: ask user if no sizes provided
if [ -z "$CAM_SIZE" ] && [ -t 0 ]; then
    echo ""
    echo "  ┌─────────────────────────────────────────┐"
    echo "  │  USB Disk Image Sizes                   │"
    echo "  ├─────────────────────────────────────────┤"
    echo "  │  Available space: ${AVAIL_GB} GB                  │"
    echo "  │                                         │"
    echo "  │  TeslaCam (dashcam):  ${SUGG_CAM} GB (suggested)     │"
    echo "  │  LightShow:            ${SUGG_LS} GB               │"
    echo "  │  Music:                ${SUGG_MUSIC} GB              │"
    echo "  └─────────────────────────────────────────┘"
    echo ""
    read -p "  TeslaCam size (GB) [${SUGG_CAM}]: " CAM_SIZE
    read -p "  LightShow size (GB) [${SUGG_LS}]: " LS_SIZE
    read -p "  Music size (GB, 0=skip) [${SUGG_MUSIC}]: " MUSIC_SIZE
fi

CAM_SIZE="${CAM_SIZE:-$SUGG_CAM}"
LS_SIZE="${LS_SIZE:-$SUGG_LS}"
MUSIC_SIZE="${MUSIC_SIZE:-$SUGG_MUSIC}"

# Validate and warn
TOTAL_NEEDED=$((CAM_SIZE + LS_SIZE + MUSIC_SIZE))
if [ "$TOTAL_NEEDED" -gt "$AVAIL_GB" ] 2>/dev/null; then
    warn "  Total image size (${TOTAL_NEEDED}GB) > available space (${AVAIL_GB}GB)"
    warn "  Images are sparse — they only use actual written data, not full size."
    warn "  Make sure you have enough headroom for actual dashcam footage."
fi

CAM_SEEK=$((CAM_SIZE * 1024))
LS_SEEK=$((LS_SIZE * 1024))
MUSIC_SEEK=$((MUSIC_SIZE * 1024))

# TeslaCam image (exFAT)
IMG_CAM="$IMAGES_DIR/usb_cam.img"
if [ ! -f "$IMG_CAM" ]; then
    log "  Creating TeslaCam image (${CAM_SIZE}GB sparse)..."
    dd if=/dev/zero of="$IMG_CAM" bs=1M count=0 seek=$CAM_SEEK status=none
    mkfs.exfat "$IMG_CAM" -n "TeslaCam" 2>/dev/null || mkfs.exfat "$IMG_CAM" -n "TeslaCam"
    log "  $IMG_CAM created (${CAM_SIZE}GB)"
fi

# LightShow image (FAT32)
IMG_LS="$IMAGES_DIR/usb_lightshow.img"
if [ ! -f "$IMG_LS" ]; then
    log "  Creating LightShow image (${LS_SIZE}GB)..."
    dd if=/dev/zero of="$IMG_LS" bs=1M count=0 seek=$LS_SEEK status=none
    mkfs.vfat "$IMG_LS" -n "LIGHTSHOW" 2>/dev/null || mkfs.vfat "$IMG_LS" -n "LIGHTSHOW"
    log "  $IMG_LS created (${LS_SIZE}GB)"
fi

# Music image (FAT32, optional)
IMG_MUSIC="$IMAGES_DIR/usb_music.img"
if [ "$MUSIC_SIZE" -gt 0 ] 2>/dev/null; then
    if [ ! -f "$IMG_MUSIC" ]; then
        log "  Creating Music image (${MUSIC_SIZE}GB sparse)..."
        dd if=/dev/zero of="$IMG_MUSIC" bs=1M count=0 seek=$MUSIC_SEEK status=none
        mkfs.vfat "$IMG_MUSIC" -n "MUSIC"
        log "  $IMG_MUSIC created (${MUSIC_SIZE}GB)"
    fi
else
    log "  Skipping Music image (size=0)"
fi

chown "$TARGET_USER:$TARGET_USER" "$IMAGES_DIR"/*.img 2>/dev/null || true
chmod 644 "$IMAGES_DIR"/*.img 2>/dev/null || true

# ── Step 9: Nginx Configuration ──
log "[9/11] Configuring Nginx..."

cat > /etc/nginx/sites-available/tjos << 'NGINX_EOF'
server {
    listen 80 default_server;
    server_name _;

    # Captive portal detection — redirect to TJOS
    location = /hotspot-detect.html { return 200 "Success"; }
    location = /library/test/success.html { return 200 "Success"; }
    location = /generate_204 { return 204; }
    location = /gen_204 { return 204; }
    location = /connecttest.txt { return 200 "Microsoft Connect Test"; }
    location = /ncsi.txt { return 200 "Microsoft NCSI"; }
    location = /success.txt { return 200 "success"; }

    # API proxy to Python backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        client_max_body_size 500M;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }

    # Static frontend (if built)
    root /opt/tesla-journey-os/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Static media files
    location /media/ {
        alias /opt/tesla-journey-os/data/media/;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/tjos /etc/nginx/sites-enabled/ 2>/dev/null || true
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
systemctl enable nginx 2>/dev/null || true
systemctl restart nginx 2>/dev/null || warn "Nginx restart failed"

# ── Step 10: systemd Services ──
log "[10/11] Installing systemd services..."

# Backend service (with hardware watchdog + auto-restart)
cat > /etc/systemd/system/tjos-backend.service << 'SVC_EOF'
[Unit]
Description=Tesla Journey OS Backend
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=600
StartLimitBurst=3

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/tesla-journey-os
Environment=PYTHONPATH=/opt/tesla-journey-os/backend
ExecStart=/opt/tesla-journey-os/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Hardware watchdog: systemd feeds /dev/watchdog, expects app to notify
# If app hangs > 30s without notifying, Pi reboots
WatchdogSec=30

# Security hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/tesla-journey-os/data /var/run /tmp
ReadOnlyPaths=/opt/tesla-journey-os/backend /opt/tesla-journey-os/frontend /opt/tesla-journey-os/config.yaml

[Install]
WantedBy=multi-user.target
SVC_EOF

# Boot USB presentation service
cat > /etc/systemd/system/tjos-present-usb.service << 'BOOT_EOF'
[Unit]
Description=Tesla Journey OS — Present USB Gadget at Boot
After=tjos-backend.service
Wants=tjos-backend.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/tesla-journey-os/venv/bin/python -c "
import sys; sys.path.insert(0, '/opt/tesla-journey-os/backend')
from app.modules.usb.gadget import usb_manager
if usb_manager.is_supported():
    usb_manager.setup()
    usb_manager.present()
    print('USB gadget presented')
else:
    print('USB gadget not supported on this system')
"
ExecStop=/opt/tesla-journey-os/venv/bin/python -c "
import sys; sys.path.insert(0, '/opt/tesla-journey-os/backend')
from app.modules.usb.gadget import usb_manager
usb_manager.edit()
"

[Install]
WantedBy=multi-user.target
BOOT_EOF

# WAL checkpoint timer
cat > /etc/systemd/system/tjos-wal-checkpoint.service << 'WAL_EOF'
[Unit]
Description=Tesla Journey OS — WAL Checkpoint

[Service]
Type=oneshot
User=pi
ExecStart=/opt/tesla-journey-os/venv/bin/python -c "
import sys; sys.path.insert(0, '/opt/tesla-journey-os/backend')
from app.modules.storage import run_checkpoint
import asyncio
asyncio.run(run_checkpoint())
"
WAL_EOF

cat > /etc/systemd/system/tjos-wal-checkpoint.timer << 'WAL_TIMER'
[Unit]
Description=Tesla Journey OS — WAL Checkpoint Timer

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
WAL_TIMER

# Hostname-based captive portal redirect via dnsmasq
cat > /etc/dnsmasq.d/tjos-captive.conf << 'DNS_EOF'
# Captive portal: redirect all DNS queries to this Pi
address=/#/192.168.4.1
DNS_EOF

systemctl daemon-reload
# WiFi monitor service (fallback AP when WiFi drops)
cat > /etc/systemd/system/tjos-wifi-monitor.service << 'WIFI_EOF'
[Unit]
Description=Tesla Journey OS — WiFi Monitor + Fallback AP
After=network-online.target

[Service]
Type=simple
ExecStart=/opt/tesla-journey-os/deploy/wifi-monitor.sh
Restart=always
RestartSec=10
StandardOutput=journal

[Install]
WantedBy=multi-user.target
WIFI_EOF

systemctl enable tjos-backend.service
systemctl enable tjos-wal-checkpoint.timer
systemctl enable tjos-wifi-monitor.service 2>/dev/null || warn "WiFi monitor enable failed"

# Only enable USB presentation if dwc2 module is loaded
if lsmod | grep -q dwc2 2>/dev/null || [ -d /sys/class/udc ]; then
    systemctl enable tjos-present-usb.service
    log "  USB gadget service enabled"
else
    warn "  USB gadget service NOT enabled (dwc2 not available — reboot?)"
fi

# ── Step 11: Start Everything ──
log "[11/11] Starting services..."
systemctl restart tjos-backend.service || warn "Backend failed to start"
systemctl start tjos-wal-checkpoint.timer 2>/dev/null || true

if systemctl is-enabled --quiet tjos-present-usb.service 2>/dev/null; then
    systemctl start tjos-present-usb.service 2>/dev/null || warn "USB gadget start failed"
fi

# ── Done ──
HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -z "$HOST_IP" ] && HOST_IP="<pi-ip-address>"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║        Tesla Journey OS — Installed!          ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║   Dashboard:  http://${HOST_IP}              ║"
echo "║   API:        http://${HOST_IP}:8000         ║"
echo "║   Health:     http://${HOST_IP}:8000/health  ║"
echo "║   Settings:   http://${HOST_IP}/settings     ║"
echo "║                                              ║"
echo "║   WiFi Hotspot (when offline):               ║"
echo "║     SSID: Tesla Journey OS                   ║"
echo "║     Pass:  (open network)                    ║"
echo "║     Captive portal auto-redirects to TJOS    ║"
echo "║                                              ║"
echo "║   Manage:                                    ║"
echo "║     sudo systemctl restart tjos-backend      ║"
echo "║     sudo journalctl -u tjos-backend -f       ║"
echo "║     cd /opt/tesla-journey-os                 ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
log "Installation complete!"
echo ""
echo "  If you plan to plug the Pi into your Tesla's USB port,"
echo "  REBOOT first to activate the dwc2 USB gadget module:"
echo "    sudo reboot"
echo ""
