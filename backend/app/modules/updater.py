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
            if time.time() - cache.get("checked_at", 0) < _CACHE_TTL:
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
        "checked_at": datetime.now().isoformat(),
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


def apply_updates() -> dict:
    """Pull updates from GitHub and apply them.

    Steps:
      1. Record current HEAD for rollback
      2. git pull origin master
      3. Check if requirements.txt changed → pip install
      4. Restart backend service
      5. If anything fails, rollback to previous HEAD
    """
    prev_head = _get_head()

    result = {
        "success": False,
        "steps": [],
        "error": None,
        "restarted": False,
    }

    try:
        # Step 1: Save current state
        result["steps"].append("Saved current HEAD for rollback")

        # Check if there are local changes
        status = subprocess.run(
            ["git", "-C", str(APP_DIR), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if status.stdout.strip():
            changes = [l.strip()[:80] for l in status.stdout.strip().split("\n")[:5]]
            result["steps"].append(f"Stashing {len(changes)} local changes")
            subprocess.run(
                ["git", "-C", str(APP_DIR), "stash"],
                capture_output=True, text=True, timeout=10,
            )

        # Step 2: Check if requirements.txt changed BEFORE pulling
        old_req = _read_file(APP_DIR / "backend" / "requirements.txt")

        # Step 3: git pull
        result["steps"].append("Pulling from GitHub...")
        pull = subprocess.run(
            ["git", "-C", str(APP_DIR), "pull", "origin", "master"],
            capture_output=True, text=True, timeout=60,
        )
        if pull.returncode != 0:
            raise Exception(f"Git pull failed: {pull.stderr.strip()[:200]}")
        result["steps"].append(f"Pull OK: {pull.stdout.strip()[:100]}")

        # Step 4: pip install if requirements changed
        new_req = _read_file(APP_DIR / "backend" / "requirements.txt")
        if old_req != new_req:
            result["steps"].append("Requirements changed — installing...")
            pip = subprocess.run(
                [str(APP_DIR / "venv" / "bin" / "pip"), "install", "-r",
                 str(APP_DIR / "backend" / "requirements.txt"), "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if pip.returncode != 0:
                raise Exception(f"Pip install failed: {pip.stderr.strip()[:200]}")
            result["steps"].append("Dependencies updated")
        else:
            result["steps"].append("No dependency changes")

        # Step 5: Restart backend
        result["steps"].append("Restarting backend...")
        restart = subprocess.run(
            ["sudo", "systemctl", "restart", "tjos-backend"],
            capture_output=True, text=True, timeout=30,
        )
        if restart.returncode != 0:
            raise Exception(f"Service restart failed: {restart.stderr.strip()[:200]}")
        result["steps"].append("Backend restarted")
        result["restarted"] = True

        # Also restart nginx if it's running
        subprocess.run(
            ["sudo", "systemctl", "reload", "nginx"],
            capture_output=True, text=True, timeout=10,
        )

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)
        result["success"] = False

        # Rollback
        if prev_head:
            result["steps"].append(f"Rolling back to {prev_head[:7]}...")
            rollback = subprocess.run(
                ["git", "-C", str(APP_DIR), "reset", "--hard", prev_head],
                capture_output=True, text=True, timeout=10,
            )
            if rollback.returncode == 0:
                result["steps"].append("Rollback OK")
                # Restart service with old code
                subprocess.run(
                    ["sudo", "systemctl", "restart", "tjos-backend"],
                    capture_output=True, text=True, timeout=30,
                )
            else:
                result["steps"].append(f"Rollback FAILED: {rollback.stderr.strip()[:100]}")

    return result


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
