"""Application paths, auth token and settings store."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

APP_NAME = "meshdeck"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8570

DEFAULT_SETTINGS: dict[str, Any] = {
    "mode": "basic",  # "basic" | "advanced"
    "display_name": "",
    "connect_autointerface": True,
    "public_entrypoints": [],  # [{"name": str, "host": str, "port": int}, ...]
    # Structured interface list (Phase 3 wizard); when non-empty it fully
    # replaces the auto/entrypoints defaults. Entry schema:
    # {kind: auto|tcp_server|tcp_client|backbone_server|backbone_client,
    #  name, enabled, listen_ip?, port?, target_host?, target_port?,
    #  gateway_mode?}
    "interfaces": [],
    "extra_config_text": "",  # advanced escape hatch, appended raw to reticulum config
    "announce_interval_minutes": 15,
    "log_level": 4,
    "transport_enabled": False,
    # Phase 2: delivery behaviour
    "delivery_method": "direct",  # "direct" | "propagated" | "opportunistic"
    "propagation_node_hash": "",  # hex hash of an LXMF propagation node
    # Phase 4: page hosting (nomadnetwork.node)
    "node_name": "",  # public name of the hosted node; empty = "<display>'s Node"
    "serve_pages": False,  # announce the node destination so others can find it
    # Phase 4: store-and-forward hosting (LXMF propagation node). Live-applied.
    "host_propagation_node": False,
    # Phase 6.3: bound disk usage. Both limits are live-applied; 0 = unlimited.
    # Page cache: total bytes for the whole offline page cache. 64 MiB default
    # (the old 500 rows x 4 MiB ceiling was ~2 GB of worst case).
    "page_cache_max_bytes": 64 * 1024 * 1024,
    # LXMF propagation message store, in MB as LXMF itself counts them
    # (decimal: 1 MB = 1,000,000 bytes, matching RNS.prettysize output).
    "propagation_storage_limit_mb": 256,
    # Phase 7.1: bound the remaining stores. All limits are live-applied;
    # 0 = unlimited. File-backed stores use MiB (1 MiB = 1,048,576 bytes);
    # only the LXMF propagation store above uses decimal MB (LXMF's unit).
    # Chat attachment blobs under files/<peer>/<msg>/ (message rows survive).
    "attachment_storage_max_mb": 512,
    # 0 = keep forever; N > 0 deletes blobs older than N days (rows survive).
    "attachment_retention_days": 0,
    # User content: never auto-deleted. New writes are refused above the cap.
    "shared_storage_max_mb": 1024,
    "pages_storage_max_mb": 256,
    # SQLite message history: 0 = keep forever; N > 0 prunes older messages
    # (peers and discovered nodes are never pruned).
    "message_retention_days": 0,
    # Our logs (logs/meshdeck.log, logs/reticulum.log): rotated at startup,
    # keeping one .1 backup. 0 = unlimited. Applies on the next start.
    "log_max_mb": 10,
}

DELIVERY_METHODS = ("direct", "propagated", "opportunistic")

VALID_MODES = ("basic", "advanced")

# Numeric setting bounds. Anything outside is rejected with 400 by the API,
# never silently clamped, so the UI can always trust the stored value.
PAGE_CACHE_MAX_BYTES_CEILING = 1024 * 1024 * 1024  # 1 GiB
PROPAGATION_STORAGE_LIMIT_MB_MAX = 10240  # 10 GiB, the UI's documented range
# Phase 7.1 bounds. Same policy: reject, never clamp.
ATTACHMENT_STORAGE_MAX_MB_MAX = 102400  # 100 GiB
SHARED_STORAGE_MAX_MB_MAX = 102400  # 100 GiB
PAGES_STORAGE_MAX_MB_MAX = 10240  # 10 GiB (pages are capped at 4 MiB each)
RETENTION_DAYS_MAX = 3650  # 10 years
LOG_MAX_MB_MAX = 1024  # 1 GiB per log file

MIB = 1024 * 1024


def mb_to_bytes(megabytes: int) -> int:
    """Binary MiB -> bytes for the file-backed stores (0 stays unlimited)."""
    return max(0, int(megabytes)) * MIB



def coerce_setting_int(key: str, value: Any, minimum: int, maximum: int) -> int:
    """Validate a numeric setting from JSON and return it as a plain int.

    Strict on purpose: booleans are ints in Python, and floats/strings would
    otherwise be stored and then applied differently at the next boot."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid_{key}")
    if value < minimum or value > maximum:
        raise ValueError(f"invalid_{key}")
    return value


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, appauthor=False))


@dataclass
class AppPaths:
    """All on-disk locations MeshDeck uses. Owns its data dir; never touches ~/.reticulum."""

    data_dir: Path

    @property
    def db_path(self) -> Path:
        return self.data_dir / "meshdeck.db"

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
    def shared_dir(self) -> Path:
        return self.data_dir / "shared"

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
