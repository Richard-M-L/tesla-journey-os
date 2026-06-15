"""Configuration loader — reads config.yaml and exports typed settings."""

from pathlib import Path
from dataclasses import dataclass, field
import yaml

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.yaml"
PROJECT_ROOT = CONFIG_PATH.parent.resolve()


@dataclass
class IngestionConfig:
    watch_dir: str = "./data/teslacam"
    archive_dir: str = "./data/archived"
    import_dir: str = "./data/import"
    sample_rate: int = 30


@dataclass
class TripConfig:
    gap_minutes: int = 5
    min_duration_seconds: int = 60
    min_distance_km: float = 0.1
    stationary_speed_mps: float = 0.5
    stationary_timeout_seconds: int = 180


@dataclass
class EventThreshold:
    enabled: bool = True
    threshold_ms2: float = 0.0


@dataclass
class EventsConfig:
    emergency_brake: EventThreshold = field(default_factory=lambda: EventThreshold(threshold_ms2=-7.0))
    harsh_brake: EventThreshold = field(default_factory=lambda: EventThreshold(threshold_ms2=-4.0))
    hard_acceleration: EventThreshold = field(default_factory=lambda: EventThreshold(threshold_ms2=3.5))
    sharp_turn: EventThreshold = field(default_factory=lambda: EventThreshold(threshold_ms2=4.0))
    speeding: dict = field(default_factory=lambda: {"enabled": True, "threshold_mps": 35.76})
    autopilot_disengage: dict = field(default_factory=lambda: {"enabled": True})
    battery_low: dict = field(default_factory=lambda: {"enabled": True, "threshold_pct": 10})


@dataclass
class StorageConfig:
    database_path: str = "./data/tjos.db"
    geodata_path: str = "./data/geodata.db"
    wal_checkpoint_interval: int = 300


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])


@dataclass
class ArchiveConfig:
    retry_attempts: int = 3
    retry_delay_seconds: int = 60
    stable_write_age: int = 30


@dataclass
class ApConfig:
    enabled: bool = True
    ssid: str = "Tesla Journey OS"
    passphrase: str = ""
    channel: int = 6
    interface: str = "wlan0"
    ipv4_cidr: str = "192.168.4.1/24"
    dhcp_start: str = "192.168.4.10"
    dhcp_end: str = "192.168.4.50"
    check_interval: int = 20
    disconnect_grace: int = 30
    min_rssi: int = -70
    stable_seconds: int = 20
    ping_target: str = "8.8.8.8"
    retry_seconds: int = 300
    virtual_interface: str = "uap0"
    force_mode: str = "auto"


@dataclass
class Config:
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    trip: TripConfig = field(default_factory=TripConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    web: WebConfig = field(default_factory=WebConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    ap: ApConfig = field(default_factory=ApConfig)


def _resolve(raw_path: str) -> str:
    p = Path(raw_path)
    if p.is_absolute():
        return str(p)
    return str(PROJECT_ROOT / p)


def load_config(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    if not path.exists():
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    ing_raw = raw.get("ingestion", {})
    stg_raw = raw.get("storage", {})

    return Config(
        ingestion=IngestionConfig(
            watch_dir=_resolve(ing_raw.get("watch_dir", "./data/teslacam")),
            archive_dir=_resolve(ing_raw.get("archive_dir", "./data/archived")),
            import_dir=_resolve(ing_raw.get("import_dir", "./data/import")),
            sample_rate=ing_raw.get("sample_rate", 30),
        ),
        trip=TripConfig(**raw.get("trip", {})),
        events=EventsConfig(
            emergency_brake=EventThreshold(**raw["events"].get("emergency_brake", {})),
            harsh_brake=EventThreshold(**raw["events"].get("harsh_brake", {})),
            hard_acceleration=EventThreshold(**raw["events"].get("hard_acceleration", {})),
            sharp_turn=EventThreshold(**raw["events"].get("sharp_turn", {})),
            speeding=raw["events"].get("speeding", {"enabled": True, "threshold_mps": 35.76}),
            autopilot_disengage=raw["events"].get("autopilot_disengage", {"enabled": True}),
            battery_low=raw["events"].get("battery_low", {"enabled": True, "threshold_pct": 10}),
        ) if "events" in raw else EventsConfig(),
        storage=StorageConfig(
            database_path=_resolve(stg_raw.get("database_path", "./data/tjos.db")),
            geodata_path=_resolve(stg_raw.get("geodata_path", "./data/geodata.db")),
            wal_checkpoint_interval=stg_raw.get("wal_checkpoint_interval", 300),
        ),
        web=WebConfig(**raw.get("web", {})),
        archive=ArchiveConfig(**raw.get("archive", {})),
        ap=ApConfig(**raw.get("offline_ap", {})),
    )


config: Config = load_config()
