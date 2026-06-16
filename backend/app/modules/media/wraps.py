"""
Wraps, License Plates & Boombox management — Tesla-compatible validation.

Adapted from TeslaUSB's wrap_service.py, license_plate_service.py, boombox_service.py.

Wraps:
  - PNG only, 512-1024px, ≤1MB, 30-char max filename, 10-file max
  - IHDR chunk parsing (no PIL dependency)

License Plates:
  - PNG output, 420×200 (NA) or 420×100 (EU) exact
  - Auto-crop/resize via FFmpeg from any input format
  - ≤512KB, alphanumeric filename (≤32 chars), 10-file max

Boombox:
  - MP3/WAV only, magic byte validation
  - ≤1MB, ≤64-char filename, 5-file max (alphabetical, Tesla reads first 5)
  - NHTSA safety notice: only plays in Park
"""

import logging
import os
import re
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from app.modules.media import WRAPS_DIR, PLATES_DIR, BOOMBOX_DIR, ensure_dirs

logger = logging.getLogger("media.wraps")

# ── PNG Header Parser (no PIL) ──

def _read_png_info(file_path: str) -> dict:
    """Read PNG dimensions from IHDR chunk header. No PIL dependency."""
    result = {"valid": False, "width": 0, "height": 0, "error": None}
    try:
        with open(file_path, "rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                result["error"] = "不是 PNG 文件"
                return result
            while True:
                chunk_len_bytes = f.read(4)
                if len(chunk_len_bytes) < 4: break
                chunk_len = struct.unpack(">I", chunk_len_bytes)[0]
                chunk_type = f.read(4)
                if chunk_type == b"IHDR":
                    if chunk_len < 13:
                        result["error"] = "IHDR 块损坏"
                        return result
                    ihdr = f.read(13)
                    result["width"] = struct.unpack(">I", ihdr[0:4])[0]
                    result["height"] = struct.unpack(">I", ihdr[4:8])[0]
                    result["valid"] = True
                    return result
                f.seek(chunk_len + 4, 1)  # skip data + CRC
        result["error"] = "未找到 IHDR 块"
    except Exception as e:
        result["error"] = str(e)
    return result


# ── Audio Validation ──

def _validate_mp3(file_path: str) -> bool:
    """Check MP3 magic bytes: ID3 tag or MPEG frame sync."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(3)
            if header[:3] == b"ID3": return True
            if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0: return True
        return False
    except OSError: return False

def _validate_wav(file_path: str) -> bool:
    """Check WAV magic bytes: RIFF...WAVE."""
    try:
        if os.path.getsize(file_path) < 12: return False
        with open(file_path, "rb") as f:
            return f.read(4) == b"RIFF" and f.read(8)[4:] == b"WAVE"
    except OSError: return False


# ═══════════════════════════════════════════════════
# WRAPS
# ═══════════════════════════════════════════════════

WRAP_MAX_SIZE = 1_048_576       # 1 MB
WRAP_MIN_DIM = 512
WRAP_MAX_DIM = 1024
WRAP_MAX_COUNT = 10
WRAP_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\- ]{1,30}$")

def list_wraps() -> list[dict]:
    ensure_dirs()
    wraps = []
    for f in sorted(WRAPS_DIR.glob("*.png")):
        info = _read_png_info(str(f))
        wraps.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "size_kb": round(f.stat().st_size / 1024, 1),
            "width": info["width"],
            "height": info["height"],
            "valid": info["valid"],
            "compliant": (WRAP_MIN_DIM <= info["width"] <= WRAP_MAX_DIM and
                         WRAP_MIN_DIM <= info["height"] <= WRAP_MAX_DIM and
                         f.stat().st_size <= WRAP_MAX_SIZE),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return wraps

def validate_wrap(filename: str, file_path: str) -> dict:
    """Full validation for a car wrap upload. Returns {valid, error, width, height}."""
    r = {"valid": False, "error": None, "width": 0, "height": 0}

    stem = Path(filename).stem
    if not filename.lower().endswith(".png"):
        r["error"] = "仅支持 PNG 格式"
        return r
    if len(stem) > 30:
        r["error"] = "文件名不能超过 30 个字符"
        return r
    if not WRAP_FILENAME_RE.match(stem):
        r["error"] = "文件名只能包含字母、数字、下划线、破折号和空格"
        return r

    info = _read_png_info(file_path)
    if not info["valid"]:
        r["error"] = info["error"]
        return r

    r["width"] = info["width"]
    r["height"] = info["height"]

    if info["width"] < WRAP_MIN_DIM or info["width"] > WRAP_MAX_DIM:
        r["error"] = f"宽度 {info['width']}px，特斯拉要求 {WRAP_MIN_DIM}-{WRAP_MAX_DIM}px"
        return r
    if info["height"] < WRAP_MIN_DIM or info["height"] > WRAP_MAX_DIM:
        r["error"] = f"高度 {info['height']}px，特斯拉要求 {WRAP_MIN_DIM}-{WRAP_MAX_DIM}px"
        return r

    size = os.path.getsize(file_path)
    if size > WRAP_MAX_SIZE:
        r["error"] = f"文件 {size/1e6:.1f} MB，特斯拉要求 ≤ 1 MB"
        return r

    r["valid"] = True
    return r

def upload_wrap(file_path: str, filename: str) -> dict:
    """Upload and validate a car wrap file."""
    ensure_dirs()
    existing = list(WRAPS_DIR.glob("*.png"))
    if len(existing) >= WRAP_MAX_COUNT:
        return {"success": False, "error": f"最多 {WRAP_MAX_COUNT} 个车衣，请先删除一个"}

    val = validate_wrap(filename, file_path)
    if not val["valid"]:
        return {"success": False, "error": val["error"]}

    dest = WRAPS_DIR / filename
    tmp = str(dest) + ".tmp"
    shutil.copy2(file_path, tmp)
    os.replace(tmp, str(dest))
    return {"success": True, "filename": filename, "size_kb": round(dest.stat().st_size/1024, 1),
            "width": val["width"], "height": val["height"]}

def delete_wrap(filename: str) -> bool:
    path = WRAPS_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False


# ═══════════════════════════════════════════════════
# LICENSE PLATES
# ═══════════════════════════════════════════════════

PLATE_MAX_SIZE = 524_288        # 512 KB
PLATE_DIMS = [(420, 200), (420, 100)]  # NA, EU
PLATE_MAX_COUNT = 10
PLATE_FILENAME_RE = re.compile(r"^[A-Za-z0-9]{1,32}$")

def list_plates() -> list[dict]:
    ensure_dirs()
    plates = []
    for f in sorted(PLATES_DIR.glob("*.png")):
        info = _read_png_info(str(f))
        w, h = info["width"], info["height"]
        size = f.stat().st_size
        ok_dims = (w == 420 and h in (100, 200))
        issues = []
        if not ok_dims: issues.append(f"尺寸 {w}x{h}，要求 420x200(NA) 或 420x100(EU)")
        if size > PLATE_MAX_SIZE: issues.append(f"文件 {size/1024:.0f}KB，上限 512KB")
        stem = f.stem
        if not PLATE_FILENAME_RE.match(stem): issues.append("文件名只能包含字母和数字")
        if len(stem) > 32: issues.append("文件名不超过 32 个字符")
        plates.append({
            "filename": f.name, "size_bytes": size, "size_kb": round(size/1024, 1),
            "width": w, "height": h, "region": "NA" if h == 200 else "EU" if h == 100 else "未知",
            "valid_dims": ok_dims, "compliant": len(issues) == 0, "issues": issues,
        })
    return plates

def plate_crop_resize(file_path: str, region: str = "NA") -> tuple[bool, str, str]:
    """Crop and resize any image to Tesla plate dimensions via FFmpeg.
    Input: PNG/JPEG/WEBP/GIF/BMP. Output: 420x200 (NA) or 420x100 (EU) PNG.
    Returns (success, error, output_path).
    """
    h = 200 if region.upper() == "NA" else 100
    tmp = tempfile.mktemp(suffix=".png")
    # FFmpeg: scale to exact dimensions, output PNG
    ok, err = _run_ffmpeg_crop(file_path, 420, h, tmp)
    if not ok:
        try: os.unlink(tmp)
        except OSError: pass
        return False, err, ""
    # Ensure output fits Tesla limits
    size = os.path.getsize(tmp)
    if size > PLATE_MAX_SIZE:
        try: os.unlink(tmp)
        except OSError: pass
        return False, f"处理后文件 {size/1024:.0f}KB 超过 512KB 上限", ""
    return True, "", tmp

def _run_ffmpeg_crop(input_path: str, w: int, h: int, output: str) -> tuple[bool, str]:
    """FFmpeg: scale to w×h, output PNG."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", input_path,
             "-vf", f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}",
             "-frames:v", "1", "-update", "1", output],
            capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False, result.stderr.strip()[-200:] or "处理失败"
        return True, ""
    except FileNotFoundError:
        return False, "FFmpeg 未安装"
    except subprocess.TimeoutExpired:
        return False, "处理超时"

def upload_plate(file_path: str, filename: str, region: str = "NA") -> dict:
    """Upload license plate image with auto-crop/resize."""
    ensure_dirs()
    stem = Path(filename).stem
    if len(stem) > 32:
        return {"success": False, "error": "文件名不超过 32 个字符"}
    if not PLATE_FILENAME_RE.match(stem):
        return {"success": False, "error": "文件名只能包含字母和数字（特斯拉车牌解析器限制）"}

    existing = list(PLATES_DIR.glob("*.png"))
    if len(existing) >= PLATE_MAX_COUNT:
        return {"success": False, "error": f"最多 {PLATE_MAX_COUNT} 个车牌"}

    # Check if already correct dimensions — skip FFmpeg
    info = _read_png_info(file_path)
    h = 200 if region.upper() == "NA" else 100
    if info["valid"] and info["width"] == 420 and info["height"] == h:
        processed = file_path  # Already compliant
    else:
        ok, err, processed = plate_crop_resize(file_path, region)
        if not ok:
            return {"success": False, "error": err}

    dest = PLATES_DIR / filename
    tmp = str(dest) + ".tmp"
    try:
        shutil.copy2(processed, tmp)
        if os.path.getsize(tmp) > PLATE_MAX_SIZE:
            os.unlink(tmp)
            return {"success": False, "error": f"处理后文件超过 512KB 上限"}
        os.replace(tmp, str(dest))
    finally:
        if processed != file_path and os.path.exists(processed):
            try: os.unlink(processed)
            except OSError: pass

    return {"success": True, "filename": filename, "region": region,
            "size_kb": round(dest.stat().st_size/1024, 1)}

def delete_plate(filename: str) -> bool:
    path = PLATES_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False


# ═══════════════════════════════════════════════════
# BOOMBOX
# ═══════════════════════════════════════════════════

BOOMBOX_MAX_SIZE = 1_048_576     # 1 MB
BOOMBOX_MAX_COUNT = 5
BOOMBOX_FILENAME_RE = re.compile(r"^[A-Za-z0-9 _\-.]+$")
BOOMBOX_MAX_FILENAME = 64

BOOMBOX_SAFETY_NOTICE = (
    "外放音效仅在驻车时播放（2022年2月 NHTSA 召回 22V-068）。"
    "车辆必须配备外部行人警告扬声器——Model 3/Y/S/X 需 2019年9月后生产。"
)

def list_boombox() -> list[dict]:
    ensure_dirs()
    files = []
    for f in sorted(BOOMBOX_DIR.iterdir()):
        if not f.is_file(): continue
        size = f.stat().st_size
        ext = f.suffix.lower()
        is_mp3 = ext == ".mp3" and _validate_mp3(str(f))
        is_wav = ext == ".wav" and _validate_wav(str(f))
        files.append({
            "filename": f.name, "size_bytes": size, "size_kb": round(size/1024, 1),
            "format": ext.replace(".", "").upper(),
            "valid": is_mp3 or is_wav,
            "compliant": (size <= BOOMBOX_MAX_SIZE and (is_mp3 or is_wav)),
        })
    return files

def validate_boombox(file_path: str, filename: str) -> dict:
    """Full Boombox validation matching Tesla restrictions."""
    r = {"valid": False, "error": None}
    ext = Path(filename).suffix.lower()
    name_only = Path(filename).stem

    if ext not in (".mp3", ".wav"):
        r["error"] = "仅支持 MP3 和 WAV 格式"
        return r
    if len(filename) > BOOMBOX_MAX_FILENAME:
        r["error"] = f"文件名不超过 {BOOMBOX_MAX_FILENAME} 个字符"
        return r
    if not BOOMBOX_FILENAME_RE.match(name_only):
        r["error"] = "文件名只能包含字母、数字、空格、下划线、破折号、点号"
        return r

    size = os.path.getsize(file_path)
    if size > BOOMBOX_MAX_SIZE:
        r["error"] = f"文件 {size/1e6:.1f} MB，特斯拉要求 ≤ 1 MB"
        return r

    if ext == ".mp3" and not _validate_mp3(file_path):
        r["error"] = "不是有效的 MP3 文件"
        return r
    if ext == ".wav" and not _validate_wav(file_path):
        r["error"] = "不是有效的 WAV 文件"
        return r

    r["valid"] = True
    return r

def upload_boombox(file_path: str, filename: str) -> dict:
    """Upload a Boombox sound with Tesla restriction enforcement."""
    ensure_dirs()
    val = validate_boombox(file_path, filename)
    if not val["valid"]:
        return {"success": False, "error": val["error"]}

    existing = [f for f in BOOMBOX_DIR.iterdir() if f.is_file()]
    if len(existing) >= BOOMBOX_MAX_COUNT and not (BOOMBOX_DIR / filename).exists():
        return {"success": False, "error": f"最多 {BOOMBOX_MAX_COUNT} 个音效（特斯拉按字母顺序加载前5个）"}

    dest = BOOMBOX_DIR / filename
    tmp = str(dest) + ".upload"
    shutil.copy2(file_path, tmp)
    with open(tmp, "r+b") as f:
        f.flush(); os.fsync(f.fileno())
    os.replace(tmp, str(dest))
    return {"success": True, "filename": filename, "format": Path(filename).suffix.replace(".","").upper()}

def delete_boombox(filename: str) -> bool:
    path = BOOMBOX_DIR / filename
    if path.exists():
        path.unlink()
        return True
    return False
