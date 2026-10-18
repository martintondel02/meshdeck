"""Peer CRUD."""

from __future__ import annotations

import time
from typing import Any

from waypoint.storage.db import Database


def upsert_peer(
    db: Database,
    hash_hex: str,
    identity_hash: str,
    display_name: str | None = None,
    stamp_cost: int | None = None,
    seen_ts: float | None = None,
) -> None:
    """Insert a newly announced peer or update its announce-derived fields."""
    seen = seen_ts if seen_ts is not None else time.time()
    db.execute(
        "INSERT INTO peers(hash, identity_hash, display_name, stamp_cost, first_seen, last_seen)"
        " VALUES(?,?,?,?,?,?)"
        " ON CONFLICT(hash) DO UPDATE SET"
        "   identity_hash = excluded.identity_hash,"
        "   display_name = COALESCE(excluded.display_name, peers.display_name),"
        "   stamp_cost = COALESCE(excluded.stamp_cost, peers.stamp_cost),"
        "   last_seen = excluded.last_seen",
        (hash_hex, identity_hash, display_name, stamp_cost, seen, seen),
    )


def ensure_peer(db: Database, hash_hex: str, identity_hash: str) -> None:
    """Create a minimal peer row if it does not exist (e.g. first inbound message
    arrives before we ever saw the peer's announce)."""
    now = time.time()
    db.execute(
        "INSERT OR IGNORE INTO peers(hash, identity_hash, first_seen, last_seen)"
        " VALUES(?,?,?,?)",
        (hash_hex, identity_hash, now, now),
    )


def list_peers(db: Database, include_blocked: bool = False) -> list[dict[str, Any]]:
    if include_blocked:
        rows = db.query("SELECT * FROM peers ORDER BY last_seen DESC")
    else:
        rows = db.query("SELECT * FROM peers WHERE blocked = 0 ORDER BY last_seen DESC")
    return [dict(r) for r in rows]


def get_peer(db: Database, hash_hex: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM peers WHERE hash = ?", (hash_hex,))
    return dict(row) if row else None


def update_peer(
    db: Database,
    hash_hex: str,
    nickname: str | None = None,
    blocked: bool | None = None,
) -> None:
    if nickname is not None:
        db.execute("UPDATE peers SET nickname = ? WHERE hash = ?", (nickname, hash_hex))
    if blocked is not None:
        db.execute(
            "UPDATE peers SET blocked = ? WHERE hash = ?", (1 if blocked else 0, hash_hex)
        )
