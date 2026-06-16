"""
SEI Parser — extracts telemetry from Tesla dashcam MP4 files.

Production-quality port of TeslaUSB's sei_parser.py.
Memory-mapped file walker that decodes protobuf-encoded telemetry
from H.264 SEI NAL units embedded in Tesla dashcam MP4 files.

Key features:
  - mmap-based reading for memory efficiency (safe on Pi Zero 2 W)
  - Real protobuf decoding via compiled SeiMetadata schema
  - MP4 box parsing for authoritative UTC timestamps (mvhd atom)
  - Sidecar JSON cache with integrity guards (size/mtime)
  - Auto-compilation of .proto file when pre-compiled pb2 is missing
"""

import json
import logging
import mmap
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Iterator, Optional

logger = logging.getLogger("ingestion.parser")

# MP4 epoch offset: QuickTime epoch (1904-01-01) → Unix epoch (1970-01-01)
_MP4_EPOCH_OFFSET = 2082844800

# Gear and autopilot enum mappings matching dashcam.proto
_GEAR_NAMES = {0: "PARK", 1: "DRIVE", 2: "REVERSE", 3: "NEUTRAL"}
_AUTOPILOT_NAMES = {0: "NONE", 1: "SELF_DRIVING", 2: "AUTOSTEER", 3: "TACC"}

# Lazy-loaded compiled protobuf class
_SeiMetadata = None
SIDECAR_SUFFIX = ".sei.json"
SIDECAR_SCHEMA_VERSION = 1


# ── Data class ──────────────────────────────────────

@dataclass
class TelemetryFrame:
    """A single decoded telemetry frame from SEI data."""
    frame_index: int = 0
    timestamp_ms: float = 0.0
    timestamp: datetime | None = None  # Absolute UTC, set by caller from mvhd

    # Motion
    speed_mps: float = 0.0
    gear: str = ""
    odometer_km: float = 0.0

    # GPS (optional — None when unavailable)
    latitude: float | None = None
    longitude: float | None = None
    heading: int | None = None

    # Acceleration
    acceleration_x: float | None = None
    acceleration_y: float | None = None
    acceleration_z: float | None = None

    # Driver inputs
    accelerator_pedal_pct: float | None = None
    brake_pedal_pct: float | None = None
    steering_angle_deg: float | None = None
    brake_applied: bool = False
    blinker_left: bool = False
    blinker_right: bool = False

    # Autopilot
    is_autopilot_on: bool = False
    autopilot_state: str = ""

    # Climate / battery (not in SEI — populated from other sources)
    battery_level_pct: float | None = None
    battery_range_km: float | None = None
    inside_temp_c: float | None = None
    outside_temp_c: float | None = None
    fan_speed: int | None = None
    is_climate_on: bool = False

    # Source
    video_path: str = ""
    frame_offset: int = 0

    @property
    def has_gps(self) -> bool:
        return self.latitude is not None and (
            self.latitude != 0.0 or self.longitude != 0.0
        )

    @property
    def speed_kmh(self) -> float:
        return abs(self.speed_mps) * 3.6


# ── Protobuf loader ─────────────────────────────────

def _get_sei_metadata_class():
    """Lazy-load the compiled protobuf class, auto-compiling if needed."""
    global _SeiMetadata
    if _SeiMetadata is not None:
        return _SeiMetadata

    # Try pre-compiled pb2 module first
    try:
        from app.modules.ingestion import dashcam_pb2
        _SeiMetadata = dashcam_pb2.SeiMetadata
        return _SeiMetadata
    except ImportError:
        pass

    # Auto-compile from .proto
    module_dir = os.path.dirname(os.path.abspath(__file__))
    proto_src = os.path.join(module_dir, "dashcam.proto")
    pb2_dst = os.path.join(module_dir, "dashcam_pb2.py")

    if not os.path.isfile(proto_src):
        raise ImportError(
            f"dashcam.proto not found at {proto_src}. "
            "Re-run setup to restore the proto file."
        )

    logger.info("Compiling dashcam.proto → dashcam_pb2.py")
    import subprocess
    try:
        subprocess.run(
            ["protoc", f"--python_out={module_dir}",
             f"--proto_path={module_dir}", proto_src],
            check=True, capture_output=True, text=True,
        )
        logger.info("dashcam_pb2.py compiled successfully")
    except FileNotFoundError:
        raise ImportError(
            "protoc compiler not found. Install: apt install protobuf-compiler"
        )
    except subprocess.CalledProcessError as e:
        raise ImportError(f"protoc failed: {e.stderr or e.stdout}")

    # Retry import after compilation
    import importlib
    try:
        dashcam_pb2 = importlib.import_module("app.modules.ingestion.dashcam_pb2")
    except ImportError:
        # Try direct import as fallback
        import sys
        sys.path.insert(0, module_dir)
        import dashcam_pb2

    _SeiMetadata = dashcam_pb2.SeiMetadata
    return _SeiMetadata


# ── MP4 Box parsing ─────────────────────────────────

def _find_box(data: bytes, start: int, end: int, name: str) -> Optional[dict]:
    """Find an MP4 box by 4-char name within a byte range."""
    pos = start
    name_bytes = name.encode("ascii")

    while pos + 8 <= end:
        size = struct.unpack(">I", data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8]

        if size == 1:
            if pos + 16 > end:
                break
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header_size = 16
        elif size == 0:
            size = end - pos
            header_size = 8
        else:
            header_size = 8

        if size < header_size:
            break
        if pos + size > end and box_type != name_bytes:
            break
        if pos + size > end:
            size = end - pos

        if box_type == name_bytes:
            return {"start": pos + header_size, "end": pos + size, "size": size - header_size}

        pos += size

    return None


def _find_box_required(data: bytes, start: int, end: int, name: str) -> dict:
    box = _find_box(data, start, end, name)
    if box is None:
        raise ValueError(f'MP4 box "{name}" not found')
    return box


def extract_mvhd_creation_time(video_path: str) -> Optional[datetime]:
    """Return the UTC start-of-recording time from the MP4 mvhd atom.

    Tesla writes the actual GPS-derived UTC start time in the mvhd
    creation_time field — this is the authoritative timestamp, independent
    of the car's onboard clock (which can drift by hours/days).
    """
    try:
        if not os.path.isfile(video_path):
            return None
        size = os.path.getsize(video_path)
        if size < 8:
            return None
    except OSError:
        return None

    f = None
    mmap_obj = None
    try:
        f = open(video_path, "rb")
        try:
            data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            mmap_obj = data
        except (ValueError, OSError):
            f.seek(0)
            data = f.read()

        moov = _find_box(data, 0, len(data), "moov")
        if moov is None:
            return None
        mvhd = _find_box(data, moov["start"], moov["end"], "mvhd")
        if mvhd is None:
            return None

        payload_start = mvhd["start"]
        if mvhd["size"] < 4:
            return None
        version = data[payload_start]

        if version == 1:
            if mvhd["size"] < 20:
                return None
            creation_time = struct.unpack(">Q", data[payload_start + 4:payload_start + 12])[0]
        else:
            if mvhd["size"] < 12:
                return None
            creation_time = struct.unpack(">I", data[payload_start + 4:payload_start + 8])[0]

        if creation_time <= _MP4_EPOCH_OFFSET:
            return None

        unix_seconds = creation_time - _MP4_EPOCH_OFFSET
        return datetime.fromtimestamp(unix_seconds, tz=timezone.utc)
    except Exception:
        logger.debug("mvhd read failed for %s", video_path, exc_info=True)
        return None
    finally:
        if mmap_obj is not None:
            try:
                mmap_obj.close()
            except Exception:
                pass
        if f is not None:
            try:
                f.close()
            except Exception:
                pass


def _get_timescale_and_durations(data: bytes) -> tuple[int, list[float]]:
    """Extract timescale and per-frame durations (ms) from MP4 moov box."""
    moov = _find_box_required(data, 0, len(data), "moov")
    trak = _find_box_required(data, moov["start"], moov["end"], "trak")
    mdia = _find_box_required(data, trak["start"], trak["end"], "mdia")

    mdhd = _find_box_required(data, mdia["start"], mdia["end"], "mdhd")
    mdhd_version = data[mdhd["start"]]
    if mdhd_version == 1:
        timescale = struct.unpack(">I", data[mdhd["start"] + 20:mdhd["start"] + 24])[0]
    else:
        timescale = struct.unpack(">I", data[mdhd["start"] + 12:mdhd["start"] + 16])[0]

    if timescale == 0:
        timescale = 30000

    minf = _find_box_required(data, mdia["start"], mdia["end"], "minf")
    stbl = _find_box_required(data, minf["start"], minf["end"], "stbl")
    stts = _find_box_required(data, stbl["start"], stbl["end"], "stts")

    entry_count = struct.unpack(">I", data[stts["start"] + 4:stts["start"] + 8])[0]

    if entry_count > 50000:
        logger.warning("Suspicious stts entry_count %d, using fallback", entry_count)
        return timescale, []

    MAX_TOTAL_SAMPLES = 10000
    durations = []
    pos = stts["start"] + 8
    for _ in range(entry_count):
        if pos + 8 > stts["end"]:
            break
        count = struct.unpack(">I", data[pos:pos + 4])[0]
        delta = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        remaining = MAX_TOTAL_SAMPLES - len(durations)
        if remaining <= 0:
            break
        if count > remaining:
            count = remaining
        duration_ms = (delta / timescale) * 1000
        durations.extend([duration_ms] * count)
        pos += 8

    return timescale, durations


# ── SEI NAL decoding ────────────────────────────────

def _strip_emulation_prevention_bytes(data: bytes) -> bytes:
    """Remove H.264 emulation prevention bytes (0x03 after 0x0000)."""
    out = bytearray()
    zeros = 0
    for byte in data:
        if zeros >= 2 and byte == 0x03:
            zeros = 0
            continue
        out.append(byte)
        zeros = zeros + 1 if byte == 0 else 0
    return bytes(out)


def _decode_sei_nal(nal_data: bytes) -> Optional[object]:
    """Decode a SEI NAL unit to a protobuf SeiMetadata message.

    Tesla SEI NAL structure:
      - Byte 0: NAL header
      - Byte 1: payload type (5 = user data unregistered)
      - Bytes 2+: 0x42 padding bytes
      - 0x69 payload size marker
      - Protobuf payload (with emulation prevention bytes)
      - Trailing 0x80 RBSP stop byte
    """
    if len(nal_data) < 4:
        return None

    i = 3
    while i < len(nal_data) and nal_data[i] == 0x42:
        i += 1

    if i <= 3 or i + 1 >= len(nal_data) or nal_data[i] != 0x69:
        return None

    try:
        payload = nal_data[i + 1:len(nal_data) - 1]
        clean_payload = _strip_emulation_prevention_bytes(payload)

        SeiMetadata = _get_sei_metadata_class()
        return SeiMetadata.FromString(clean_payload)
    except ImportError:
        raise
    except Exception:
        logger.debug("SEI NAL decode failed", exc_info=True)
        return None


# ── Main parsing entry point ────────────────────────

def extract_sei_messages(
    video_path: str,
    sample_rate: int = 30,
    max_walk_bytes: int | None = None,
) -> Generator[TelemetryFrame, None, None]:
    """Extract telemetry frames from a Tesla dashcam MP4 file.

    Generator yielding TelemetryFrame objects. Uses mmap for
    memory-efficient scanning of large files.

    Args:
        max_walk_bytes: Stop walking mdat after this many bytes.
            Use for fast peeks (e.g. stationary detection).
        video_path: Path to the MP4 file.
        sample_rate: Only process every Nth frame (30 = ~1/sec at 30fps).
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    file_size = os.path.getsize(video_path)
    if file_size < 8:
        raise ValueError(f"File too small: {video_path}")
    if file_size > 150 * 1024 * 1024:
        raise ValueError(f"File too large ({file_size / 1024 / 1024:.0f} MB): {video_path}")

    f = open(video_path, "rb")
    mmap_obj = None
    try:
        try:
            data = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            mmap_obj = data
        except (ValueError, OSError):
            f.seek(0)
            data = f.read()

        # Parse frame timing from moov
        try:
            timescale, durations = _get_timescale_and_durations(data)
        except ValueError:
            timescale = 30000
            durations = []
        default_duration_ms = 33.33

        # Walk NAL units in mdat box
        mdat = _find_box(data, 0, len(data), "mdat")
        if mdat is None:
            raise ValueError(f"No mdat box found in {video_path}")

        # MP4 uses LENGTH-PREFIXED NAL units (not Annex B start codes)
        cursor = mdat["start"]
        end = mdat["end"]

        # Apply max_walk_bytes limit for fast peeks
        if max_walk_bytes is not None and max_walk_bytes > 0:
            walk_stop = mdat["start"] + max_walk_bytes
            if walk_stop < end:
                end = walk_stop

        frame_index = 0
        cumulative_time_ms = 0.0

        while cursor + 4 <= end:
            nal_size = struct.unpack(">I", data[cursor:cursor + 4])[0]
            cursor += 4

            if nal_size < 1 or cursor + nal_size > len(data):
                break

            nal_type = data[cursor] & 0x1F

            if nal_type == 6:  # SEI NAL unit
                if frame_index % sample_rate == 0:
                    nal_data = data[cursor:cursor + nal_size]
                    if nal_size >= 2 and nal_data[1] == 5:
                        sei = _decode_sei_nal(nal_data)
                        if sei is not None:
                            duration_ms = (
                                durations[frame_index] if frame_index < len(durations)
                                else default_duration_ms
                            )

                            autopilot_raw = _AUTOPILOT_NAMES.get(sei.autopilot_state, "NONE")

                            yield TelemetryFrame(
                                frame_index=frame_index,
                                timestamp_ms=cumulative_time_ms,
                                speed_mps=sei.vehicle_speed_mps,
                                gear=_GEAR_NAMES.get(sei.gear_state, "UNKNOWN"),
                                latitude=sei.latitude_deg if sei.latitude_deg != 0 or sei.longitude_deg != 0 else None,
                                longitude=sei.longitude_deg if sei.latitude_deg != 0 or sei.longitude_deg != 0 else None,
                                heading=int(sei.heading_deg) if sei.heading_deg else None,
                                acceleration_x=sei.linear_acceleration_mps2_x,
                                acceleration_y=sei.linear_acceleration_mps2_y,
                                acceleration_z=sei.linear_acceleration_mps2_z,
                                accelerator_pedal_pct=sei.accelerator_pedal_position,
                                steering_angle_deg=sei.steering_wheel_angle,
                                brake_applied=sei.brake_applied,
                                blinker_left=sei.blinker_on_left,
                                blinker_right=sei.blinker_on_right,
                                is_autopilot_on=autopilot_raw in ("SELF_DRIVING", "AUTOSTEER", "TACC"),
                                autopilot_state=autopilot_raw,
                                video_path=video_path,
                            )

            elif nal_type in (1, 5):  # Non-IDR or IDR slice → advance frame
                if frame_index < len(durations):
                    cumulative_time_ms += durations[frame_index]
                else:
                    cumulative_time_ms += default_duration_ms
                frame_index += 1

            cursor += nal_size

    finally:
        if mmap_obj is not None:
            try:
                mmap_obj.close()
            except (BufferError, ValueError):
                pass
        try:
            f.close()
        except OSError:
            pass


# ── SeiParser class (TJOS interface) ────────────────

class SeiParser:
    """High-level parser that integrates sidecar caching.

    Usage:
        parser = SeiParser("/path/to/video.mp4")
        for frame in parser.parse():
            print(f"Frame {frame.frame_index}: {frame.speed_kmh:.0f} km/h")
    """

    def __init__(self, video_path: str | Path, sample_rate: int = 30):
        self.video_path = str(video_path)
        self._sidecar_path = self.video_path + SIDECAR_SUFFIX
        self.sample_rate = sample_rate

    def parse(self) -> Iterator[TelemetryFrame]:
        """Parse telemetry frames, preferring sidecar cache when valid.

        All frames get absolute UTC timestamps from the MP4 mvhd atom,
        regardless of whether they came from sidecar or direct parse.
        Timestamps are naive UTC (no tzinfo) for SQLite compatibility.
        """
        mvhd_dt = extract_mvhd_creation_time(self.video_path)
        # Strip timezone for SQLite compatibility (store as naive UTC)
        if mvhd_dt is not None:
            mvhd_dt = mvhd_dt.replace(tzinfo=None)

        sidecar = self._read_sidecar()
        if sidecar is not None:
            for frame in sidecar:
                if mvhd_dt is not None and frame.timestamp is None:
                    from datetime import timedelta
                    frame.timestamp = mvhd_dt + timedelta(milliseconds=frame.timestamp_ms)
                yield frame
            return

        for frame in extract_sei_messages(self.video_path, sample_rate=self.sample_rate):
            frame.frame_offset = frame.frame_index
            frame.video_path = self.video_path
            if mvhd_dt is not None:
                from datetime import timedelta
                frame.timestamp = mvhd_dt + timedelta(milliseconds=frame.timestamp_ms)
            yield frame

    def parse_all(self) -> list[TelemetryFrame]:
        """Parse all frames into a list. Use parse() for memory efficiency."""
        return list(self.parse())

    # ── Sidecar cache ──────────────────────────────

    def _read_sidecar(self) -> Optional[list[TelemetryFrame]]:
        """Read and validate the sidecar JSON cache."""
        path = self._sidecar_path
        if not os.path.isfile(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError):
            return None

        if not isinstance(payload, dict):
            return None

        try:
            if int(payload.get("schema_version", 0)) != SIDECAR_SCHEMA_VERSION:
                return None
            if int(payload.get("sample_rate", 0)) != self.sample_rate:
                return None
            cached_size = int(payload["video_size_bytes"])
            cached_mtime = float(payload["video_mtime_unix"])
            msgs = payload["messages"]
        except (KeyError, TypeError, ValueError):
            return None

        # Integrity guard: video file must match
        try:
            st = os.stat(self.video_path)
        except OSError:
            return None
        if st.st_size != cached_size:
            logger.debug("Sidecar invalidated: size drift for %s", os.path.basename(self.video_path))
            return None
        if abs(st.st_mtime - cached_mtime) > 0.001:
            logger.debug("Sidecar invalidated: mtime drift for %s", os.path.basename(self.video_path))
            return None

        if not isinstance(msgs, list):
            return None

        frames = []
        for m in msgs:
            try:
                frames.append(TelemetryFrame(
                    frame_index=int(m["frame_index"]),
                    timestamp_ms=float(m["timestamp_ms"]),
                    speed_mps=float(m["vehicle_speed_mps"]),
                    gear=str(m.get("gear_state", "")),
                    latitude=float(m["latitude_deg"]) if m.get("latitude_deg") not in (0, 0.0, None) else None,
                    longitude=float(m["longitude_deg"]) if m.get("longitude_deg") not in (0, 0.0, None) else None,
                    heading=int(m["heading_deg"]) if m.get("heading_deg") else None,
                    acceleration_x=float(m["linear_acceleration_x"]) if m.get("linear_acceleration_x") is not None else None,
                    acceleration_y=float(m["linear_acceleration_y"]) if m.get("linear_acceleration_y") is not None else None,
                    acceleration_z=float(m["linear_acceleration_z"]) if m.get("linear_acceleration_z") is not None else None,
                    accelerator_pedal_pct=float(m["accelerator_pedal_position"]) if m.get("accelerator_pedal_position") is not None else None,
                    steering_angle_deg=float(m["steering_wheel_angle"]) if m.get("steering_wheel_angle") is not None else None,
                    brake_applied=bool(m.get("brake_applied", False)),
                    blinker_left=bool(m.get("blinker_on_left", False)),
                    blinker_right=bool(m.get("blinker_on_right", False)),
                    is_autopilot_on=str(m.get("autopilot_state", "")) in ("SELF_DRIVING", "AUTOSTEER", "TACC"),
                    autopilot_state=str(m.get("autopilot_state", "")),
                    video_path=self.video_path,
                ))
            except (KeyError, TypeError, ValueError):
                logger.debug("Malformed sidecar message, falling back to mmap")
                return None

        logger.debug("Sidecar loaded: %d frames from %s", len(frames), os.path.basename(self.video_path))
        return frames

    def write_sidecar(self, frames: list[TelemetryFrame]) -> None:
        """Write parsed frames to sidecar JSON cache (atomic write)."""
        import os as _os

        payload = {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "sample_rate": self.sample_rate,
            "sei_count": len(frames),
            "no_gps_count": sum(1 for f in frames if not f.has_gps),
            "mvhd_creation_time_utc": None,
            "video_size_bytes": _os.path.getsize(self.video_path),
            "video_mtime_unix": _os.path.getmtime(self.video_path),
            "messages": [
                {
                    "frame_index": f.frame_index,
                    "timestamp_ms": f.timestamp_ms,
                    "vehicle_speed_mps": f.speed_mps,
                    "gear_state": f.gear,
                    "latitude_deg": f.latitude,
                    "longitude_deg": f.longitude,
                    "heading_deg": f.heading,
                    "linear_acceleration_x": f.acceleration_x,
                    "linear_acceleration_y": f.acceleration_y,
                    "linear_acceleration_z": f.acceleration_z,
                    "accelerator_pedal_position": f.accelerator_pedal_pct,
                    "steering_wheel_angle": f.steering_angle_deg,
                    "brake_applied": f.brake_applied,
                    "blinker_on_left": f.blinker_left,
                    "blinker_on_right": f.blinker_right,
                    "autopilot_state": f.autopilot_state,
                }
                for f in frames
            ],
        }

        tmp_path = self._sidecar_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, separators=(",", ":"))
                fh.flush()
                try:
                    _os.fsync(fh.fileno())
                except OSError:
                    pass
            _os.replace(tmp_path, self._sidecar_path)
            logger.debug("Sidecar written: %s", self._sidecar_path)
        except OSError:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass
