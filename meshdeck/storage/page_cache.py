"""Offline cache for pages fetched from other nodes (DB schema v3)."""

from __future__ import annotations

import time
from typing import Any

from meshdeck.storage.db import Database

# Same per-page ceiling as PageStore: never cache more than 4 MiB of markup.
MAX_CACHE_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 3600
DEFAULT_MAX_ROWS = 500


class PageCache:
    """Content-addressed-by-(node, path) cache; one row per page."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def put(
        self,
        node_hash: str,
        path: str,
        content: str,
        fetched_ts: float | None = None,
    ) -> bool:
        """Store/refresh a page. Returns False if it exceeds the size cap."""
        encoded = content.encode("utf-8", "replace")
        if len(encoded) > MAX_CACHE_BYTES:
            return False
        ts = time.time() if fetched_ts is None else fetched_ts
        self.db.execute(
            """
            INSERT INTO page_cache(node_hash, path, content, content_bytes, fetched_ts)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(node_hash, path) DO UPDATE SET
              content = excluded.content,
              content_bytes = excluded.content_bytes,
              fetched_ts = excluded.fetched_ts
            """,
            (node_hash, path, content, len(encoded), ts),
        )
        return True

    def get(self, node_hash: str, path: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT node_hash, path, content, content_bytes, fetched_ts "
            "FROM page_cache WHERE node_hash = ? AND path = ?",
            (node_hash, path),
        )
        return dict(row) if row is not None else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT node_hash, path, content_bytes, fetched_ts FROM page_cache "
            "ORDER BY fetched_ts DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in rows]

    def prune(
        self,
        older_than_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        max_rows: int = DEFAULT_MAX_ROWS,
    ) -> None:
        """Drop old entries, then cap the total row count (newest kept)."""
        cutoff = time.time() - older_than_seconds
        self.db.execute("DELETE FROM page_cache WHERE fetched_ts < ?", (cutoff,))
        self.db.execute(
            "DELETE FROM page_cache WHERE rowid NOT IN ("
            "  SELECT rowid FROM page_cache ORDER BY fetched_ts DESC LIMIT ?"
            ")",
            (max_rows,),
        )
