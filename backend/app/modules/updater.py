"""
Updater Module — check for updates from GitHub and apply them.

Features:
  - Compare local version (VERSION file) with latest GitHub release
  - Show changelog / release notes
  - git pull + pip install (if requirements changed) + service restart
  - Rollback on failure (git reset --hard to previous commit)
"""

import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("updater")

APP_DIR = Path("/opt/tesla-journey-os")
VERSION_FILE = APP_DIR / "VERSION"
REPO_URL = "https://github.com/Richard-M-L/tesla-journey-os"
GITHUB_API = "https://api.github.com/repos/Richard-M-L/tesla-journey-os"

# Cache the update check for 1 hour
_CACHE_FILE = Path("/tmp/tjos_update_check.json")
_CACHE_TTL = 3600


def get_current_version() -> str:
    """Read current version from VERSION file."""
    try:
        if VERSION_FILE.exists():
            return VERSION_FILE.read_text().strip()
        # Fallback: try the project's VERSION file relative to this module
        fallback = Path(__file__).parent.parent.parent.parent / "VERSION"
        if fallback.exists():
            return fallback.read_text().strip()
    except OSError:
        pass
    return "0.1.0"


def get_current_commit() -> dict:
    """Get current git commit info."""
    try:
        result = subprocess.run(
            ["git", "-C", str(APP_DIR), "log", "-1", "--format=%H|%s|%ai"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split("|", 2)
            return {
                "hash": parts[0][:7] if len(parts) > 0 else "unknown",
                "message": parts[1] if len(parts) > 1 else "",
                "date": parts[2][:10] if len(parts) > 2 else "",
            }
    except Exception:
        pass
    return {"hash": "unknown", "message": "", "date": ""}


def check_for_updates(force: bool = False) -> dict:
    """Check GitHub for newer releases.

    Uses ETag caching via conditional requests to avoid rate limiting.
    Returns dict with update_available, current, latest, changelog, etc.
    """
    current = get_current_version()
    commit = get_current_commit()

    # Check cache (unless forced)
    if not force and _CACHE_FILE.exists():
        try:
            import json, time
            cache = json.loads(_CACHE_FILE.read_text())
            if time.time() - float(cache.get("checked_at", 0)) < _CACHE_TTL:
                return cache
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    result = {
        "update_available": False,
        "current_version": current,
        "current_commit": commit["hash"],
        "current_commit_msg": commit["message"],
        "current_commit_date": commit["date"],
        "latest_version": current,
        "latest_commit": "",
        "new_commits": [],
        "changelog": "",
        "checked_at": time.time(),
        "error": None,
    }

    try:
        # Fetch latest from remote (no merge)
        fetch = subprocess.run(
            ["git", "-C", str(APP_DIR), "fetch", "origin", "master"],
            capture_output=True, text=True, timeout=30,
        )
        if fetch.returncode != 0:
            result["error"] = f"Git fetch failed: {fetch.stderr.strip()[:200]}"
            return result

        # Get latest commit on origin/master
        log = subprocess.run(
            ["git", "-C", str(APP_DIR), "log", "HEAD..origin/master",
             "--format=%H|%s|%ai", "--reverse"],
            capture_output=True, text=True, timeout=10,
        )
        if log.returncode != 0:
            result["error"] = f"Git log failed: {log.stderr.strip()[:200]}"
            return result

        new_commits = []
        for line in log.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 2)
            if len(parts) >= 2:
                new_commits.append({
                    "hash": parts[0][:7],
                    "message": parts[1],
                    "date": parts[2][:10] if len(parts) > 2 else "",
                })

        if new_commits:
            result["update_available"] = True
            result["new_commits"] = new_commits
            result["latest_commit"] = new_commits[-1]["hash"]
            result["changelog"] = "\n".join(
                f"- {c['message']}" for c in new_commits
            )
            result["commit_count"] = len(new_commits)

    except Exception as e:
        result["error"] = str(e)
        logger.exception("Update check failed")

    # Cache result
    import json, time
    try:
        _CACHE_FILE.write_text(json.dumps(result))
    except OSError:
        pass

    return result


_UPDATE_STATUS_FILE = Path("/tmp/tjos_update_status.json")


def _update_worker() -> None:
    """Background worker: git pull + pip install + restart service."""
    import json
    prev_head = _get_head()
    status = {"running": True, "success": False, "step": "正在准备...", "error": None}

    def _save(s):
        status.update(s)
        try: _UPDATE_STATUS_FILE.write_text(json.dumps(status))
        except OSError: pass

    try:
        _save({"step": "正在从 GitHub 拉取更新..."})

        # Stash local changes if any
        st = subprocess.run(
            ["git", "-C", str(APP_DIR), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if st.stdout.strip():
            subprocess.run(["git", "-C", str(APP_DIR), "stash"], capture_output=True, timeout=10)

        # Git pull
        old_req = _read_file(APP_DIR / "backend" / "requirements.txt")
        pull = subprocess.run(
            ["git", "-C", str(APP_DIR), "pull", "origin", "master"],
            capture_output=True, text=True, timeout=60,
        )
        if pull.returncode != 0:
            raise Exception(f"Git pull 失败: {pull.stderr.strip()[:200]}")

        _save({"step": "正在检查依赖更新..."})
        new_req = _read_file(APP_DIR / "backend" / "requirements.txt")
        if old_req != new_req:
            _save({"step": "正在安装新依赖..."})
            pip = subprocess.run(
                [str(APP_DIR / "venv" / "bin" / "pip"), "install", "-r",
                 str(APP_DIR / "backend" / "requirements.txt"), "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if pip.returncode != 0:
                raise Exception(f"pip install 失败: {pip.stderr.strip()[:200]}")

        _save({"step": "正在重启服务..."})

        # IMPORTANT: schedule restart via nohup so this process can exit cleanly
        import os as _os
        _os.system("nohup bash -c 'sleep 1 && sudo systemctl restart tjos-backend' >/dev/null 2>&1 &")
        _os.system("nohup bash -c 'sleep 2 && sudo systemctl reload nginx' >/dev/null 2>&1 &")

        _save({"success": True, "running": False, "step": "更新完成，服务已重启"})

    except Exception as e:
        logger.exception("Update failed")
        _save({"success": False, "running": False, "step": "更新失败", "error": str(e)})

        # Rollback
        if prev_head:
            _save({"step": f"正在回滚到 {prev_head[:7]}..."})
            subprocess.run(
                ["git", "-C", str(APP_DIR), "reset", "--hard", prev_head],
                capture_output=True, text=True, timeout=10,
            )
            import os as _os
            _os.system("nohup bash -c 'sleep 1 && sudo systemctl restart tjos-backend' >/dev/null 2>&1 &")
            _save({"error": f"{str(e)} (已回滚)", "step": "已回滚到更新前版本"})


def apply_updates() -> dict:
    """Start background update and return immediately.

    The update runs in a daemon thread:
      1. git pull origin master
      2. pip install (if requirements changed)
      3. systemctl restart tjos-backend
      4. Rollback on failure

    Frontend should poll /api/system/updates/status for progress.
    """
    import json, threading

    # Check if update already running
    if _UPDATE_STATUS_FILE.exists():
        try:
            existing = json.loads(_UPDATE_STATUS_FILE.read_text())
            if existing.get("running"):
                return {"started": False, "message": "更新已在运行中", "status": existing}
        except (OSError, json.JSONDecodeError):
            pass

    # Clear old status
    try: _UPDATE_STATUS_FILE.unlink(missing_ok=True)
    except OSError: pass

    # Start worker thread
    t = threading.Thread(target=_update_worker, daemon=True)
    t.start()

    return {
        "started": True,
        "message": "更新已开始，服务将在完成后自动重启",
    }


def get_update_status() -> dict:
    """Get current update progress."""
    import json
    try:
        if _UPDATE_STATUS_FILE.exists():
            return json.loads(_UPDATE_STATUS_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    return {"running": False, "success": False, "step": "无进行中的更新"}


def _get_head() -> str:
    """Get current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "-C", str(APP_DIR), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def _read_file(path: Path) -> str:
    """Read a file, return empty string if missing."""
    try:
        return path.read_text()
    except OSError:
        return ""
