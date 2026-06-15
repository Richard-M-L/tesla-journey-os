#!/usr/bin/env bash
# Tesla Journey OS — Raspberry Pi Setup Script
#
# Usage:
#   chmod +x setup_pi.sh && sudo ./setup_pi.sh
#
# This script:
#   1. Installs system dependencies (Python, protoc, etc.)
#   2. Creates a Python virtual environment
#   3. Compiles the dashcam protobuf schema
#   4. Initializes the database
#   5. Installs the systemd service
#   6. Starts the backend

set -euo pipefail

APP_DIR="/opt/tesla-journey-os"
DATA_DIR="${APP_DIR}/data"
VENV_DIR="${APP_DIR}/venv"

echo "=== Tesla Journey OS — Pi Setup ==="

# ── 1. System dependencies ──
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.13 python3.13-venv python3.13-dev \
    protobuf-compiler \
    git \
    curl

# ── 2. Create directories ──
echo "[2/6] Creating directories..."
sudo mkdir -p "${APP_DIR}" "${DATA_DIR}" "${DATA_DIR}/teslacam" "${DATA_DIR}/archived"
sudo chown -R pi:pi "${APP_DIR}"

# ── 3. Python virtual environment ──
echo "[3/6] Setting up Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    python3.13 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip -q
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/backend/requirements.txt" -q

# ── 4. Compile protobuf ──
echo "[4/6] Compiling dashcam.proto..."
PROTO_DIR="${APP_DIR}/backend/app/modules/ingestion"
if [ -f "${PROTO_DIR}/dashcam.proto" ]; then
    protoc --python_out="${PROTO_DIR}" --proto_path="${PROTO_DIR}" "${PROTO_DIR}/dashcam.proto"
    echo "  Protobuf compiled: ${PROTO_DIR}/dashcam_pb2.py"
else
    echo "  WARNING: dashcam.proto not found — parser will auto-compile at runtime"
fi

# ── 5. Initialize database ──
echo "[5/6] Initializing database..."
cd "${APP_DIR}"
PYTHONPATH="${APP_DIR}/backend" "${VENV_DIR}/bin/python" -c "
from app.database import init_db
init_db()
print('  Database initialized')
"

# ── 6. Install systemd service ──
echo "[6/6] Installing systemd service..."
sudo cp "${APP_DIR}/deploy/tesla-journey-os.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tesla-journey-os.service
sudo systemctl restart tesla-journey-os.service

echo ""
echo "=== Setup complete ==="
echo "Backend: http://$(hostname -I | awk '{print $1}'):8000"
echo "Health:  curl http://localhost:8000/health"
echo "Logs:    sudo journalctl -u tesla-journey-os -f"
echo ""
echo "To install the frontend separately:"
echo "  cd ${APP_DIR}/frontend && npm install && npm run build"
