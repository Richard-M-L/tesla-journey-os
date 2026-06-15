# Tesla Journey OS

**Local-first driving behavior analysis platform for Tesla vehicles. GPS is optional.**

Turn your Raspberry Pi into a digital twin for your Tesla. Plug it into the car's USB port — it appears as a USB drive, captures dashcam footage, extracts telemetry, detects trips and driving events, and provides a rich web dashboard. All processing happens locally. No cloud required.

## Why

Tesla vehicles in China and certain regions cannot access GPS telemetry. Tesla Journey OS was built from the ground up to work without GPS — trip detection relies on speed, gear state, and timestamps instead of coordinates. Every feature gracefully degrades when GPS is unavailable.

## Features

### Core Pipeline
- **SEI Telemetry Extraction** — Parses protobuf-encoded telemetry from Tesla dashcam MP4 files using memory-mapped I/O (safe on Pi Zero 2 W with 512MB RAM)
- **Trip Detection** — Identifies driving sessions from speed transitions, gear changes, and time gaps — no GPS needed
- **Event Detection** — Detects emergency braking, harsh braking, hard acceleration, sharp turns, speeding, and autopilot disengagement from per-frame acceleration data
- **Distance Estimation** — Falls back to speed×time integration when GPS coordinates are unavailable

### USB Gadget Mode
- Presents the Pi as **3 USB mass storage devices** to the car (TeslaCam RW, LightShow RO, Music RO)
- Tesla writes dashcam footage directly to the Pi
- Pi simultaneously reads and processes footage while the car records
- Present/Edit mode switching via web UI or shell scripts

### Web Dashboard
- **Dashboard** — Trip count, driving score, energy efficiency, GPS coverage
- **Timeline** — Chronological trip list with stats preview
- **Trip Details** — Speed profile chart, waypoint list, event markers
- **Events** — Filterable event log by type and severity
- **Statistics** — Charts for daily trips, battery trends, driving score
- **Video Browser** — Stream dashcam videos with real-time HUD telemetry overlay (speed, gear, AP state, brake, blinkers, steering angle)
- **Storage Analytics** — Disk usage pie charts, per-folder breakdown, recording time estimates
- **Map** — Optional Leaflet map view (gracefully hidden when GPS unavailable)

### Media Management
- **Lock Chimes** — Upload, validate, normalize WAV files with scheduling and chime groups
- **Light Shows** — Extract and manage .fseq + audio files from ZIP archives
- **Music** — Upload MP3/FLAC/WAV/AAC/M4A files
- **Boombox** — Manage up to 5 custom external speaker sounds
- **Custom Wraps** — Validate and manage Tesla car wrap PNG images
- **License Plates** — Manage custom license plate images (NA/EU formats)
- **USB Export** — One-click sync all media to a USB drive for the car

### Connectivity
- **WiFi Manager** — Scan, connect, saved networks, signal strength
- **Offline Hotspot** — Automatic fallback AP when WiFi drops (in-car access)
- **Captive Portal** — Intercepts OS detection probes (Apple/Android/Windows/Firefox), redirects to dashboard
- **Settings** — WiFi config, AP SSID/password, advanced tuning (event thresholds, trip parameters)

### System Protection
- **Hardware Watchdog** — `/dev/watchdog` feeding with systemd integration (Pi reboots if app hangs)
- **Safe Mode** — Detects 3+ system reboots in 10 minutes → disables heavy services, keeps SSH + AP alive
- **Task Coordinator** — Global lock prevents concurrent SDIO-heavy operations on Pi Zero 2 W
- **File Safety Guards** — Prevents accidental deletion of disk images and database files

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Raspberry Pi                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ usb_cam  │  │ usb_ls   │  │ usb_music        │  │
│  │ .img     │  │ .img     │  │ .img             │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────────────┘  │
│       └──────────────┼─────────────┘                 │
│                 ConfigFS Gadget                       │
│                 (3 LUNs via USB)                      │
└──────────────────────┬──────────────────────────────┘
                       │ USB cable
                   ┌───▼────┐
                   │  Tesla │
                   └────────┘

Backend:  Python 3 + FastAPI + SQLAlchemy + SQLite
          └── Event Bus (async pub/sub, no Redis/MQ)

Frontend: React + TypeScript + Tailwind CSS + Recharts + Leaflet

Deploy:   Docker Compose or bare-metal systemd
```

## Quick Start

### Prerequisites

- Raspberry Pi (Zero 2 W, 3, 4, or 5) running Raspberry Pi OS Bookworm
- MicroSD card (16GB minimum, 64GB+ recommended)
- USB cable to connect Pi to Tesla

### One-Command Install

```bash
# Copy project to Pi
rsync -av --exclude 'node_modules' --exclude '__pycache__' \
  ./ pi@<pi-ip>:/opt/tesla-journey-os/

# SSH in and install
ssh pi@<pi-ip>
cd /opt/tesla-journey-os
sudo ./deploy/install.sh
sudo reboot
```

The installer will:
- Install system dependencies
- Enable USB gadget kernel support (dwc2)
- Create Python virtual environment
- Build the React frontend
- Initialize the database
- Create USB disk images (with interactive size selection)
- Configure Nginx reverse proxy
- Install systemd services
- Start everything

### Custom Disk Image Sizes

```bash
# Interactive (detects free space, asks for each size)
sudo ./deploy/install.sh

# Non-interactive (TeslaCam GB, LightShow GB, Music GB)
sudo ./deploy/install.sh 32 2 16

# Skip Music partition
sudo ./deploy/install.sh 32 2 0
```

### After Install

| Service | URL |
|---------|-----|
| Dashboard | `http://<pi-ip>` |
| API | `http://<pi-ip>:8000` |
| Health | `http://<pi-ip>:8000/health` |
| Settings | `http://<pi-ip>/settings` |

When WiFi drops, the Pi creates a hotspot: **SSID:** `Tesla Journey OS` (no password by default). Connect and open any browser — the captive portal redirects to the dashboard.

### Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev           # → http://localhost:5173

# Tests
pytest tests/ -v
```

## GPS Handling

Every component checks for GPS availability and degrades gracefully:

| Component | With GPS | Without GPS |
|-----------|----------|-------------|
| Trip Detection | Haversine distance | Speed × time integration |
| Map | Leaflet with polylines | Hidden, shows explanation |
| Events | Geo-tagged | Timestamp-tagged |
| Dashboard | GPS coverage % shown | Banner: "GPS unavailable" |
| Video HUD | Coordinates display | "No GPS" indicator |

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # YAML config loader
│   │   ├── database.py          # SQLAlchemy engine
│   │   ├── event_bus.py         # Async pub/sub
│   │   ├── models/              # ORM models (8 tables)
│   │   ├── modules/
│   │   │   ├── ingestion/       # SEI parser + file watcher
│   │   │   ├── telemetry/       # Ingestion pipeline
│   │   │   ├── trip/            # Trip detection engine
│   │   │   ├── event/           # Driving event detection
│   │   │   ├── geo/             # Reverse geocoding
│   │   │   ├── analytics/       # Statistics engine
│   │   │   ├── archive/         # File archival
│   │   │   ├── storage/         # DB maintenance
│   │   │   ├── query/           # Read queries
│   │   │   ├── usb/             # ConfigFS gadget manager
│   │   │   ├── media/           # Lock chimes, light shows, etc.
│   │   │   ├── wifi.py          # WiFi management (nmcli)
│   │   │   ├── ap.py            # Access point service
│   │   │   ├── video.py         # Video streaming + telemetry
│   │   │   ├── storage_analytics.py
│   │   │   ├── task_coordinator.py
│   │   │   ├── watchdog.py      # Hardware watchdog + safe mode
│   │   │   ├── file_safety.py
│   │   │   └── captive_portal.py
│   │   └── api/routes.py        # 62 REST endpoints
│   └── scan.py                  # CLI bulk video scanner
├── frontend/
│   └── src/
│       ├── pages/               # 20+ page components
│       ├── components/          # Layout, sidebar, etc.
│       ├── hooks/               # Custom React hooks
│       ├── lib/                 # API client, utilities
│       └── types/               # TypeScript definitions
├── deploy/
│   ├── install.sh               # One-click Pi installer
│   ├── present_usb.sh           # USB gadget mode: present
│   ├── edit_usb.sh              # USB gadget mode: edit
│   └── wifi-monitor.sh          # WiFi health + AP fallback
├── tests/                       # pytest smoke tests
└── config.yaml                  # Unified configuration
```

## Configuration

All settings in `config.yaml`:

```yaml
ingestion:
  watch_dir: "/mnt/tjos_gadget/part1-ro/TeslaCam"
  sample_rate: 30

trip:
  gap_minutes: 5
  min_duration_seconds: 60

events:
  emergency_brake:
    threshold_ms2: -7.0
  harsh_brake:
    threshold_ms2: -4.0
  hard_acceleration:
    threshold_ms2: 3.5

offline_ap:
  ssid: "Tesla Journey OS"
  passphrase: ""
  channel: 6

usb_gadget:
  enabled: true
  images:
    cam:
      size: "64G"
      filesystem: exfat
    lightshow:
      size: "4G"
      filesystem: fat32
    music:
      size: "32G"
      filesystem: fat32
      enabled: true
```

Settings can also be changed via the web UI at `/settings`.

## API

62 REST endpoints. Key groups:

| Prefix | Description |
|--------|-------------|
| `/api/stats` | Dashboard statistics |
| `/api/trips` | Trip listing, detail, telemetry |
| `/api/events` | Driving events |
| `/api/analytics` | Charts, scores, trends |
| `/api/videos` | Browse, stream, telemetry |
| `/api/wifi` | Scan, connect, saved networks |
| `/api/ap` | Hotspot status, config |
| `/api/usb` | Gadget status, mode switching |
| `/api/media/*` | Lock chimes, light shows, music, wraps, plates, boombox |
| `/api/storage` | Disk usage, video stats |
| `/api/settings` | Config read/write |
| `/api/system` | Health, safe mode, reboot history |
| `/api/geo` | Reverse geocoding |
| `/health` | Quick health check |

## Acknowledgements

Built on the foundation of [TeslaUSB](https://github.com/cimryan/teslausb), the original Raspberry Pi Tesla dashcam solution. Tesla Journey OS reimagines the concept as a telemetry-first driving behavior platform with GPS-optional architecture.

## License

MIT
