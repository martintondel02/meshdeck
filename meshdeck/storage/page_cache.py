"""Offline cache for pages fetched from other nodes (DB schema v3).

Two ceilings bound what this cache can take from the disk:

* ``MAX_CACHE_BYTES`` — one page never exceeds 4 MiB (same cap as PageStore);
* ``max_bytes`` (setting ``page_cache_max_bytes``, default 64 MiB, 0 = no
  limit) — the whole cache stays under this, enforced on every put by
  evicting the oldest rows first. The row-count/age prune at boot is a second
  belt, not the primary bound.
"""

from __future__ import annotations

import time
from typing import Any

from meshdeck.storage.db import Database

# Same per-page ceiling as PageStore: never cache more than 4 MiB of markup.
MAX_CACHE_BYTES = 4 * 1024 * 1024
# Total-cache ceiling used when no explicit limit is configured.
DEFAULT_MAX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 3600
DEFAULT_MAX_ROWS = 500

# SQLite's default host-parameter limit is 999; delete evictions in batches.
_EVICT_BATCH = 400


class PageCache:
    """Content-addressed-by-(node, path) cache; one row per page."""

    def __init__(self, db: Database, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.db = db
        self.max_bytes = max(0, int(max_bytes))

    # -- writes ---------------------------------------------------------------

    def put(
        self,
        node_hash: str,
        path: str,
        content: str,
        fetched_ts: float | None = None,
    ) -> bool:
        """Store/refresh a page. Returns False if it cannot fit the caps.

        Room is made *before* inserting (oldest rows first, excluding the row
        being refreshed), so a successful put is always within ``max_bytes``
        afterwards and the fresh entry is never the one evicted.
        """
        encoded = content.encode("utf-8", "replace")
        size = len(encoded)
        if size > MAX_CACHE_BYTES:
            return False
        if self.max_bytes and size > self.max_bytes:
            # A single page larger than the whole-cache ceiling can never be
            # kept; refusing is better than thrashing the cache to hold it.
            return False
        ts = time.time() if fetched_ts is None else fetched_ts
        self._make_room(size, node_hash, path)
        self.db.execute(
            """
            INSERT INTO page_cache(node_hash, path, content, content_bytes, fetched_ts)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(node_hash, path) DO UPDATE SET
              content = excluded.content,
              content_bytes = excluded.content_bytes,
              fetched_ts = excluded.fetched_ts
            """,
            (node_hash, path, content, size, ts),
        )
        return True

    def _make_room(self, incoming_bytes: int, node_hash: str, path: str) -> int:
        """Evict oldest rows until ``incoming_bytes`` fits. Returns rows dropped."""
        if not self.max_bytes:
            return 0
        replaced = self.db.execute(
            "SELECT rowid, content_bytes FROM page_cache WHERE node_hash = ? AND path = ?",
            (node_hash, path),
        )
        replaced_rowid = int(replaced["rowid"]) if replaced is not None else None
        used = self.total_bytes()
        if replaced is not None:
            # The row is about to be overwritten, so its bytes are free already.
            used -= int(replaced["content_bytes"] or 0)
        if used + incoming_bytes <= self.max_bytes:
            return 0
        excess = used + incoming_bytes - self.max_bytes
        candidates = self.db.query(
            "SELECT rowid, content_bytes FROM page_cache "
            "ORDER BY fetched_ts ASC, rowid ASC"
        )
        victims: list[int] = []
        freed = 0
        for row in candidates:
            if freed >= excess:
                break
            rowid = int(row["rowid"])
            if rowid == replaced_rowid:
                continue
            victims.append(rowid)
            freed += int(row["content_bytes"] or 0)
        self._delete_rowids(victims)
        return len(victims)

    def _delete_rowids(self, rowids: list[int]) -> int:
        for start in range(0, len(rowids), _EVICT_BATCH):
            batch = rowids[start : start + _EVICT_BATCH]
            placeholders = ",".join("?" * len(batch))
            self.db.execute(
                f"DELETE FROM page_cache WHERE rowid IN ({placeholders})",  # noqa: S608 - placeholders only
                tuple(batch),
            )
        return len(rowids)

    def set_max_bytes(self, max_bytes: int) -> int:
        """Live-apply a new ceiling, shrinking the cache immediately."""
        self.max_bytes = max(0, int(max_bytes))
        return self._enforce_max_bytes()

    def clear(self) -> int:
        """Drop every cached page; returns how many rows were removed."""
        removed = self.count()
        self.db.execute("DELETE FROM page_cache")
        return removed

    # -- reads ----------------------------------------------------------------

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

    def total_bytes(self) -> int:
        row = self.db.execute(
            "SELECT COALESCE(SUM(content_bytes), 0) AS total FROM page_cache"
        )
        return int(row["total"] or 0) if row is not None else 0

    def count(self) -> int:
        row = self.db.execute("SELECT COUNT(*) AS n FROM page_cache")
        return int(row["n"] or 0) if row is not None else 0

    # -- maintenance ----------------------------------------------------------

    def prune(
        self,
        older_than_seconds: float = DEFAULT_MAX_AGE_SECONDS,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_bytes: int | None = None,
    ) -> int:
        """Drop stale entries, cap the row count, then enforce the byte cap.

        ``max_bytes=None`` means "use the cache's configured ceiling" (pass 0
        explicitly for no byte ceiling). Returns the number of rows removed."""
        before = self.count()
        cutoff = time.time() - older_than_seconds
        self.db.execute("DELETE FROM page_cache WHERE fetched_ts < ?", (cutoff,))
        self.db.execute(
            "DELETE FROM page_cache WHERE rowid NOT IN ("
            "  SELECT rowid FROM page_cache ORDER BY fetched_ts DESC LIMIT ?"
            ")",
            (max_rows,),
        )
        if max_bytes is not None:
            self.max_bytes = max(0, int(max_bytes))
        self._enforce_max_bytes()
        return before - self.count()

    def _enforce_max_bytes(self) -> int:
        """Evict oldest rows until the cache is at or below ``max_bytes``."""
        if not self.max_bytes:
            return 0
        total = self.total_bytes()
        if total <= self.max_bytes:
            return 0
        excess = total - self.max_bytes
        rows = self.db.query(
            "SELECT rowid, content_bytes FROM page_cache "
            "ORDER BY fetched_ts ASC, rowid ASC"
        )
        victims: list[int] = []
        freed = 0
        for row in rows:
            if freed >= excess:
                break
            victims.append(int(row["rowid"]))
            freed += int(row["content_bytes"] or 0)
        return self._delete_rowids(victims)
