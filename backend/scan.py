#!/usr/bin/env python3
"""
Tesla Journey OS — Manual Video Scanner

Scans a directory for Tesla dashcam MP4 files and runs the full
ingestion pipeline on each one.

Usage:
  python scan.py /path/to/TeslaCam          # Scan a specific directory
  python scan.py                             # Use config.yaml watch_dir
  python scan.py --dry-run /path/to/TeslaCam # List files without processing
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scan")

DRY_RUN = "--dry-run" in sys.argv


async def scan_directory(watch_dir: str) -> dict:
    """Scan a directory and ingest all MP4 files via the event bus pipeline."""
    from app.database import init_db
    from app.event_bus import Event, EventType, event_bus

    init_db()
    await event_bus.start()

    # Register modules so telemetry/trip/event engines are listening
    from app.modules.telemetry import register as reg_telemetry
    from app.modules.trip import register as reg_trip
    from app.modules.event import register as reg_event
    await reg_telemetry()
    await reg_trip()
    await reg_event()

    watch_path = Path(watch_dir)
    if not watch_path.exists():
        logger.error("Directory not found: %s", watch_dir)
        await event_bus.stop()
        return {"error": f"Directory not found: {watch_dir}"}

    mp4_files = sorted(watch_path.glob("**/*.mp4"))
    logger.info("Found %d MP4 files in %s", len(mp4_files), watch_dir)

    if DRY_RUN:
        for f in mp4_files:
            size_mb = f.stat().st_size / (1024 * 1024)
            print(f"  {f.name} ({size_mb:.1f} MB)")
        await event_bus.stop()
        return {"dry_run": True, "files_found": len(mp4_files)}

    # Emit FILE_DETECTED for each file — triggers full pipeline
    processed = 0
    errors = 0
    for i, mp4 in enumerate(mp4_files):
        logger.info("[%d/%d] Processing: %s", i + 1, len(mp4_files), mp4.name)
        await event_bus.emit(Event(
            type=EventType.FILE_DETECTED,
            data={"path": str(mp4.absolute()), "size": mp4.stat().st_size},
        ))
        processed += 1
        # Give the pipeline time to process between files
        await asyncio.sleep(1)

    # Let the event queue drain
    logger.info("Waiting for pipeline to finish...")
    await asyncio.sleep(3)

    # Show results
    from app.modules.query import get_stats_overview
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        stats = get_stats_overview(db)
        print("\n" + "=" * 50)
        print("  SCAN COMPLETE")
        print("=" * 50)
        print(f"  Files processed:    {processed}")
        print(f"  Total trips:        {stats['total_trips']}")
        print(f"  Total events:       {stats['total_events']}")
        print(f"  Total snapshots:    {stats['total_telemetry_snapshots']}")
        print(f"  Total distance:     {stats['total_distance_km']} km")
        print(f"  Trips with GPS:     {stats['trips_with_gps_pct']}%")
        print("=" * 50)
    finally:
        db.close()

    await event_bus.stop()
    return {"processed": processed, "errors": errors, "stats": "see above"}


if __name__ == "__main__":
    # Determine watch directory
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        watch_dir = sys.argv[1]
    else:
        from app.config import config
        watch_dir = config.ingestion.watch_dir

    asyncio.run(scan_directory(watch_dir))
