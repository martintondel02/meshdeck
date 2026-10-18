"""Storage helpers for discovered NomadNet-style page hosting nodes."""

from __future__ import annotations

import time
from typing import Any

from waypoint.storage.db import Database


def upsert_node(db: Database, node_hash: str, name: str | None) -> None:
    now = time.time()
    db.execute(
        "INSERT INTO nodes(hash, name, first_seen, last_seen)"
        " VALUES(?, ?, ?, ?)"
        " ON CONFLICT(hash) DO UPDATE SET name = COALESCE(?, name), last_seen = ?",
        (node_hash, name, now, now, name, now),
    )


def list_nodes(db: Database) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT hash, name, first_seen, last_seen FROM nodes ORDER BY last_seen DESC"
    )
    return [dict(r) for r in rows]
