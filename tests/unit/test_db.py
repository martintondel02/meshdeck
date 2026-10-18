"""DB migrations and CRUD."""

import time

from waypoint.storage import messages as msg_repo
from waypoint.storage import nodes as node_repo
from waypoint.storage import peers as peer_repo
from waypoint.storage.db import Database


def test_migrate_creates_schema(tmp_path):
    with Database(tmp_path / "t.db") as db:
        assert db.user_version == 2
        tables = {r[0] for r in db.query("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"settings", "peers", "messages", "nodes"} <= tables


def test_migrate_is_idempotent(tmp_path):
    with Database(tmp_path / "t.db") as db:
        db.migrate()
        db.migrate()
        assert db.user_version == 2


def test_peer_upsert_and_patch(tmp_path):
    with Database(tmp_path / "t.db") as db:
        peer_repo.upsert_peer(db, "aa" * 16, "bb" * 16, display_name="Alice", stamp_cost=8)
        peers = peer_repo.list_peers(db)
        assert len(peers) == 1
        assert peers[0]["display_name"] == "Alice"
        assert peers[0]["stamp_cost"] == 8

        # re-announce with no name must keep the old one
        peer_repo.upsert_peer(db, "aa" * 16, "bb" * 16, display_name=None)
        assert peer_repo.list_peers(db)[0]["display_name"] == "Alice"

        peer_repo.update_peer(db, "aa" * 16, nickname="Ally", blocked=True)
        assert peer_repo.list_peers(db) == []  # blocked hidden by default
        peer = peer_repo.get_peer(db, "aa" * 16)
        assert peer["nickname"] == "Ally"
        assert peer["blocked"] == 1


def test_nodes_repo(tmp_path):
    with Database(tmp_path / "t.db") as db:
        node_repo.upsert_node(db, "cc" * 16, "Test Node")
        node_repo.upsert_node(db, "cc" * 16, None)  # keep existing name
        nodes = node_repo.list_nodes(db)
        assert len(nodes) == 1
        assert nodes[0]["name"] == "Test Node"
        node_repo.upsert_node(db, "cc" * 16, "Renamed Node")
        assert node_repo.list_nodes(db)[0]["name"] == "Renamed Node"


def test_message_lifecycle(tmp_path):
    with Database(tmp_path / "t.db") as db:
        peer_repo.ensure_peer(db, "cc" * 16, "dd" * 16)
        msg_repo.insert_message(
            db,
            {"hash": "ef" * 16, "peer_hash": "cc" * 16, "direction": "out",
             "state": "sending", "content": "hello", "created_ts": time.time()},
        )
        rows = msg_repo.list_messages(db, "cc" * 16)
        assert len(rows) == 1 and rows[0]["state"] == "sending"

        msg_repo.update_message_state(db, "ef" * 16, "delivered", delivered_ts=time.time())
        row = msg_repo.get_message(db, "ef" * 16)
        assert row["state"] == "delivered"
        assert row["delivered_ts"] is not None
