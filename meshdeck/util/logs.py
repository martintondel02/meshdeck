"""Startup log rotation for MeshDeck-owned log files.

Only files inside MeshDeck's own ``logs/`` directory are touched:
``meshdeck.log`` and the generated ``reticulum.log``. ``log_max_mb`` (default
10, 0 = unlimited) is read from the settings table *before* logging/RNS starts,
then each oversized file is renamed to ``<name>.1`` (replacing an older backup).
The new file is created by the writer itself.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from meshdeck.config import DEFAULT_SETTINGS, LOG_MAX_MB_MAX, AppPaths

log = logging.getLogger(__name__)

MANAGED_LOGS = ("meshdeck.log", "reticulum.log")


def stored_log_max_mb(db_path: Path) -> int:
    """Read ``log_max_mb`` without booting the service; default on any doubt."""
    default = int(DEFAULT_SETTINGS["log_max_mb"])
    if not db_path.is_file():
        return default
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'log_max_mb'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return default
    if row is None:
        return default
    try:
        value = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    if value < 0 or value > LOG_MAX_MB_MAX:
        return default
    return value


def rotate_log(path: Path, max_bytes: int) -> dict[str, object]:
    """Rename *path* to ``path.1`` when it is over *max_bytes* (0 = unlimited)."""
    result: dict[str, object] = {
        "path": str(path),
        "rotated": False,
        "bytes": 0,
        "backup": None,
    }
    if max_bytes <= 0 or not path.is_file():
        return result
    try:
        size = path.stat().st_size
    except OSError:
        return result
    result["bytes"] = size
    if size <= max_bytes:
        return result
    backup = Path(str(path) + ".1")
    try:
        if backup.exists():
            backup.unlink()
        path.replace(backup)
    except OSError:
        log.exception("could not rotate log file %s", path)
        return result
    result["rotated"] = True
    result["backup"] = str(backup)
    log.info("rotated %s (%s bytes) -> %s", path.name, size, backup.name)
    return result


def rotate_app_logs(paths: AppPaths, log_max_mb: int) -> list[dict[str, object]]:
    max_bytes = max(0, int(log_max_mb)) * 1024 * 1024
    return [rotate_log(paths.logs_dir / name, max_bytes) for name in MANAGED_LOGS]


def log_usage(paths: AppPaths) -> dict[str, int]:
    """Bytes used by managed logs plus their one backup generation."""
    total = 0
    for name in MANAGED_LOGS:
        for path in (paths.logs_dir / name, Path(str(paths.logs_dir / name) + ".1")):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
    return {"log_bytes": total}


def prepare_logging(paths: AppPaths) -> Path:
    """Rotate managed logs using the stored limit, return MeshDeck's log path."""
    paths.ensure()
    max_mb = stored_log_max_mb(paths.db_path)
    rotate_app_logs(paths, max_mb)
    return paths.logs_dir / "meshdeck.log"
