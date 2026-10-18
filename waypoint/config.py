"""Application paths, auth token and settings store."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

APP_NAME = "waypoint"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8570

DEFAULT_SETTINGS: dict[str, Any] = {
    "mode": "basic",  # "basic" | "advanced"
    "display_name": "",
    "connect_autointerface": True,
    "public_entrypoints": [],  # [{"name": str, "host": str, "port": int}, ...]
    "extra_config_text": "",  # advanced escape hatch, appended raw to reticulum config
    "announce_interval_minutes": 15,
    "log_level": 4,
    "transport_enabled": False,
}

VALID_MODES = ("basic", "advanced")


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False))


@dataclass
class AppPaths:
    """All on-disk locations Waypoint uses. Owns its data dir; never touches ~/.reticulum."""

    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "waypoint.db"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token"

    @property
    def identity_path(self) -> Path:
        return self.data_dir / "identity"

    @property
    def reticulum_dir(self) -> Path:
        return self.data_dir / "reticulum"

    @property
    def reticulum_config_path(self) -> Path:
        return self.reticulum_dir / "config"

    @property
    def lxmf_dir(self) -> Path:
        return self.data_dir / "lxmf"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    def ensure(self) -> None:
        for p in (
            self.data_dir,
            self.reticulum_dir,
            self.lxmf_dir,
            self.files_dir,
            self.pages_dir,
            self.logs_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)


def load_or_create_token(path: Path) -> str:
    """Load the local API auth token, generating a fresh one on first run."""
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    os.chmod(path, 0o600)
    return token


class SettingsStore:
    """Settings persisted in SQLite as JSON values, overlaid on DEFAULT_SETTINGS."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        if default is None:
            default = DEFAULT_SETTINGS.get(key)
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        self._db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )

    def all(self) -> dict[str, Any]:
        merged = dict(DEFAULT_SETTINGS)
        for row in self._db.query("SELECT key, value FROM settings"):
            try:
                merged[row[0]] = json.loads(row[1])
            except (json.JSONDecodeError, TypeError):
                continue
        return merged
