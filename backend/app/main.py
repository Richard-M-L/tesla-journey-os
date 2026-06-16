"""
Tesla Journey OS — FastAPI Application Entry Point.

Local-first, single-vehicle digital twin platform.
GPS is optional. Telemetry is the source of truth.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import config
from app.database import init_db
from app.event_bus import event_bus
from app.api import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tjos")

# ── System protection singletons ──
watchdog_runner = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the application."""
    global watchdog_runner

    # Startup
    logger.info("Tesla Journey OS starting...")

    # Safe mode check — skip heavy services if too many recent reboots
    from app.modules.watchdog import safe_mode
    safe_mode.record_boot()
    if safe_mode.is_safe_mode():
        logger.error("!!! SAFE MODE ACTIVE — Heavy services disabled !!!")
        logger.error("Manual recovery: DELETE /var/run/tjos_safe_mode and restart")
        # Still start web server + event bus so admin can access settings
    else:
        init_db()

    await event_bus.start()

    if not safe_mode.is_safe_mode():
        await _register_modules()

    # Start hardware watchdog (keeps Pi alive if app hangs)
    from app.modules.watchdog import hardware_watchdog
    hardware_watchdog.start()

    logger.info("Tesla Journey OS ready")
    yield

    # Shutdown
    logger.info("Tesla Journey OS shutting down...")
    hardware_watchdog.stop()
    await event_bus.stop()


async def _register_modules() -> None:
    """Register all modules with the event bus on startup."""
    from app.modules.telemetry import register as reg_telemetry
    from app.modules.trip import register as reg_trip
    from app.modules.event import register as reg_event
    from app.modules.archive import register as reg_archive

    await reg_telemetry()
    await reg_trip()
    await reg_event()
    await reg_archive()

    logger.info("All modules registered")


app = FastAPI(
    title="Tesla Journey OS",
    description="Local-first driving behavior analysis platform for Tesla vehicles",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.web.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Captive portal — must be registered at root level for OS detection
from app.modules.captive_portal import router as portal_router
app.include_router(portal_router)


# Catch-all redirect: any unknown URL → dashboard (captive portal behavior)
@app.get("/{path:path}")
async def catch_all(path: str):
    """Catch-all route for captive portal. Redirects unknown URLs to the dashboard.
    Skips known API/static paths to avoid interfering with real routes."""
    skip_prefixes = ("api/", "health", "static/", "media/export", "settings", "videos")
    if any(path.startswith(p) for p in skip_prefixes):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Not found"}, status_code=404)
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/")


@app.get("/health")
async def health():
    from app.modules.storage import get_storage_health
    from app.modules.watchdog import safe_mode, archive_watchdog
    from app.modules.task_coordinator import coordinator
    return {
        "status": "ok",
        "storage": get_storage_health(),
        "safe_mode": safe_mode.is_safe_mode(),
        "task_coordinator": coordinator.get_status(),
        "archive_watchdog": archive_watchdog.check(queue_depth=0, worker_running=True),
    }
