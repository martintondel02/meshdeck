"""Message CRUD."""

from __future__ import annotations

import time
from typing import Any

from meshdeck.storage.db import Database

INBOUND = "in"
OUTBOUND = "out"

# message states
SENDING = "sending"
SENT = "sent"
DELIVERED = "delivered"
FAILED = "failed"
RECEIVED = "received"


def insert_message(db: Database, msg: dict[str, Any]) -> None:
    db.execute(
        "INSERT OR IGNORE INTO messages"
        "(hash, peer_hash, direction, state, method, title, content, fields_json,"
        " created_ts, delivered_ts) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (
            msg["hash"],
            msg["peer_hash"],
            msg["direction"],
            msg["state"],
            msg.get("method"),
            msg.get("title"),
            msg.get("content"),
            msg.get("fields_json"),
            msg.get("created_ts", time.time()),
            msg.get("delivered_ts"),
        ),
    )


def update_message_state(
    db: Database, msg_hash: str, state: str, delivered_ts: float | None = None
) -> None:
    db.execute(
        "UPDATE messages SET state = ?, delivered_ts = COALESCE(?, delivered_ts)"
        " WHERE hash = ?",
        (state, delivered_ts, msg_hash),
    )


def get_message(db: Database, msg_hash: str) -> dict[str, Any] | None:
    row = db.execute("SELECT * FROM messages WHERE hash = ?", (msg_hash,))
    return dict(row) if row else None


def list_messages(
    db: Database,
    peer_hash: str,
    before: float | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Newest-first, paginated backwards by *before* timestamp."""
    if before is not None:
        rows = db.query(
            "SELECT * FROM messages WHERE peer_hash = ? AND created_ts < ?"
            " ORDER BY created_ts DESC LIMIT ?",
            (peer_hash, before, limit),
        )
    else:
        rows = db.query(
            "SELECT * FROM messages WHERE peer_hash = ?"
            " ORDER BY created_ts DESC LIMIT ?",
            (peer_hash, limit),
        )
    return [dict(r) for r in rows]
