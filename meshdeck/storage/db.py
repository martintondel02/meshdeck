"""SQLite storage: connection handling and hand-rolled migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS peers(
  hash TEXT PRIMARY KEY,
  identity_hash TEXT NOT NULL,
  display_name TEXT,
  nickname TEXT,
  stamp_cost INTEGER,
  first_seen REAL,
  last_seen REAL,
  blocked INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  hash TEXT UNIQUE NOT NULL,
  peer_hash TEXT NOT NULL REFERENCES peers(hash),
  direction TEXT NOT NULL,
  state TEXT NOT NULL,
  method INTEGER,
  title TEXT,
  content TEXT,
  fields_json TEXT,
  created_ts REAL,
  delivered_ts REAL
);
CREATE INDEX IF NOT EXISTS idx_messages_peer ON messages(peer_hash, created_ts);
"""

# Ordered migrations: (target user_version, SQL)
MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
    (2, """
CREATE TABLE IF NOT EXISTS nodes(
  hash TEXT PRIMARY KEY,          -- nomadnetwork.node destination hash
  name TEXT,                      -- announced node name
  first_seen REAL,
  last_seen REAL
);
"""),
    (3, """
CREATE TABLE IF NOT EXISTS page_cache(
  node_hash TEXT NOT NULL,
  path TEXT NOT NULL,
  content TEXT NOT NULL,
  content_bytes INTEGER,
  fetched_ts REAL,
  PRIMARY KEY(node_hash, path)
);
CREATE INDEX IF NOT EXISTS idx_page_cache_ts ON page_cache(fetched_ts);
"""),
]


class Database:
    """One guarded SQLite connection. All access goes through the service layer,
    which serializes writes (see docs: single-writer discipline)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.conn = sqlite3.connect(
            str(self.path), check_same_thread=False, isolation_level=None
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    def migrate(self) -> None:
        assert self.conn is not None
        current = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for target_version, sql in MIGRATIONS:
            if current < target_version:
                with self.conn:
                    self.conn.executescript(sql)
                    self.conn.execute(f"PRAGMA user_version = {target_version}")
                current = target_version

    @property
    def user_version(self) -> int:
        assert self.conn is not None
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Run a single statement; returns the first row if any."""
        assert self.conn is not None
        with self.conn:
            cur = self.conn.execute(sql, params)
            return cur.fetchone()

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        assert self.conn is not None
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> Database:
        self.open()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
