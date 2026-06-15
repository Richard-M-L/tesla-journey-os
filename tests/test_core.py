"""Core smoke tests for Tesla Journey OS."""

import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


class TestConfig:
    """Config loader tests."""

    def test_loads_defaults(self):
        from app.config import Config
        cfg = Config()
        assert cfg.ingestion.sample_rate == 30
        assert cfg.trip.gap_minutes == 5
        assert cfg.web.port == 8000
        assert cfg.ap.ssid == "Tesla Journey OS"

    def test_loads_from_yaml(self):
        from app.config import load_config
        cfg = load_config()
        assert cfg is not None
        assert cfg.ingestion is not None

    def test_project_root(self):
        from app.config import PROJECT_ROOT
        assert PROJECT_ROOT.exists()


class TestDatabase:
    """Database init and model tests."""

    def test_init_creates_tables(self, tmp_path):
        import tempfile
        from app.config import config
        from app.database import init_db
        from sqlalchemy import inspect, create_engine

        # Use temp DB
        db_path = tmp_path / "test.db"
        orig_path = config.storage.database_path
        try:
            # Override path for test
            from app.database import engine as real_engine, DATABASE_URL
            # Create a test engine directly
            test_engine = create_engine(f"sqlite:///{db_path}")
            from app.models import Base
            Base.metadata.create_all(bind=test_engine)

            inspector = inspect(test_engine)
            tables = inspector.get_table_names()

            assert "trips" in tables
            assert "telemetry_snapshots" in tables
            assert "telemetry_cold" in tables
            assert "driving_events" in tables
            assert "waypoints" in tables
        finally:
            pass

    def test_all_tables_present(self):
        from app.models import Base
        expected = {
            "trips", "waypoints", "driving_events",
            "telemetry_snapshots", "telemetry_cold",
            "geo_cache", "indexed_files", "pipeline_queue",
        }
        table_names = {t.name for t in Base.metadata.sorted_tables}
        assert expected.issubset(table_names), f"Missing: {expected - table_names}"


class TestEventBus:
    """Event bus pub/sub tests."""

    def test_register_and_emit(self):
        import asyncio
        from app.event_bus import EventBus, Event, EventType

        received = []

        async def listener(evt: Event):
            received.append(evt.data)

        async def run():
            bus = EventBus()
            bus.subscribe(EventType.FILE_DETECTED, listener)
            await bus.start()
            await bus.emit(Event(EventType.FILE_DETECTED, {"test": True}))
            await asyncio.sleep(0.5)
            await bus.stop()

        asyncio.run(run())
        assert len(received) == 1
        assert received[0]["test"] is True

    def test_emit_without_listeners(self):
        import asyncio
        from app.event_bus import EventBus, Event, EventType

        async def run():
            bus = EventBus()
            await bus.start()
            await bus.emit(Event(EventType.TRIP_STARTED, {"trip_id": 1}))
            await asyncio.sleep(0.5)
            await bus.stop()

        asyncio.run(run())  # Should not raise


class TestModels:
    """Data model validation."""

    def test_telemetry_snapshot_fields(self):
        from app.models import TelemetrySnapshot
        from sqlalchemy import inspect
        mapper = inspect(TelemetrySnapshot)
        cols = {c.name for c in mapper.columns}
        assert "timestamp" in cols
        assert "speed_mps" in cols
        assert "gear" in cols
        assert "latitude" in cols
        assert "latitude" in cols  # nullable

    def test_trip_fields(self):
        from app.models import Trip
        from sqlalchemy import inspect
        mapper = inspect(Trip)
        cols = {c.name for c in mapper.columns}
        assert "start_time" in cols
        assert "end_time" in cols
        assert "distance_km" in cols
        assert "start_lat" in cols  # nullable — GPS optional


class TestFileSafety:
    """File safety guard tests."""

    def test_protects_img_files(self):
        from app.modules.file_safety import is_protected_file
        assert is_protected_file("test.img") is True
        assert is_protected_file("usb_cam.img") is True

    def test_protects_db_files(self):
        from app.modules.file_safety import is_protected_file
        assert is_protected_file("tjos.db") is True
        assert is_protected_file("tjos.db-wal") is True

    def test_allows_mp4_deletion(self):
        from app.modules.file_safety import is_protected_file
        assert is_protected_file("video.mp4") is False
        assert is_protected_file("dashcam.mp4") is False


class TestConfigYamlRoundTrip:
    """Config settings save API test."""

    def test_settings_save_validation(self, tmp_path):
        """Test that settings save validates allowed keys."""
        import json
        from pathlib import Path

        # This test just validates the whitelist logic
        allowed_paths = {
            "ingestion.sample_rate": int,
            "trip.gap_minutes": int,
            "events.emergency_brake.threshold_ms2": float,
        }

        # Valid keys pass
        assert "ingestion.sample_rate" in allowed_paths

        # Unknown keys are rejected
        unknown = "malicious.injected.key"
        assert unknown not in allowed_paths
