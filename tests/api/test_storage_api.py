"""Phase 7.1 API acceptance against a REAL ``python -m meshdeck`` subprocess.

Why a subprocess: ``RNS.Reticulum`` is a process singleton, so one pytest
process cannot boot two in-process daemons (test_api.py boots one). The CLI
subprocess also lets us verify startup log rotation for real.

Hermetic: temp data dir, no interfaces (``connect_autointerface=False``), OS
chosen loopback port, real bearer token, SIGTERM teardown.
"""

from __future__ import annotations

import json
import os
import time

import aiohttp
import pytest

from meshdeck.config import AppPaths, SettingsStore
from meshdeck.core.service import NUMERIC_SETTINGS
from meshdeck.storage import messages as msg_repo
from meshdeck.storage import peers as peer_repo
from meshdeck.storage.db import Database
from tests.api.test_routes import Daemon, free_port

pytestmark = pytest.mark.integration

PEER = "ab" * 16
ATTACH_MSG = "cd" * 32
OLD_MSG = "ef" * 32


def _seed(tmp_path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "wp")
    paths.ensure()
    db = Database(paths.db_path)
    db.open()
    try:
        store = SettingsStore(db)
        store.set("connect_autointerface", False)
        store.set("log_max_mb", 1)
        peer_repo.ensure_peer(db, PEER, "11" * 32)

        blob_dir = paths.files_dir / PEER / ATTACH_MSG
        blob_dir.mkdir(parents=True)
        blob = blob_dir / "0_old.bin"
        blob.write_bytes(b"hello")
        when = time.time() - 10 * 86400
        os.utime(blob, (when, when))

        msg_repo.insert_message(
            db,
            {
                "hash": ATTACH_MSG,
                "peer_hash": PEER,
                "direction": msg_repo.INBOUND,
                "state": msg_repo.RECEIVED,
                "content": "file follows",
                "fields_json": json.dumps(
                    {"attachments": [{"index": 0, "name": "old.bin", "size": 5}]}
                ),
                "created_ts": time.time(),
            },
        )
        msg_repo.insert_message(
            db,
            {
                "hash": OLD_MSG,
                "peer_hash": PEER,
                "direction": msg_repo.INBOUND,
                "state": msg_repo.RECEIVED,
                "content": "ancient",
                "created_ts": time.time() - 30 * 86400,
            },
        )
    finally:
        db.close()
    # Real oversized logs written *before* the daemon starts.
    for name in ("meshdeck.log", "reticulum.log"):
        (paths.logs_dir / name).write_bytes(b"x" * (2 * 1024 * 1024))
    return paths


async def test_storage_bounds_endtoend(tmp_path):
    paths = _seed(tmp_path)
    daemon = Daemon(data_dir=paths.data_dir, http_port=free_port()).start()
    base, auth = daemon.base, daemon.auth
    try:
        async with aiohttp.ClientSession() as session:
            # -- status surface
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                assert r.status == 200
                body = await r.json()
            for key in (
                "attachment_bytes",
                "attachment_files",
                "attachment_storage_max_bytes",
                "attachment_retention_days",
                "shared_bytes",
                "shared_files",
                "shared_storage_max_bytes",
                "pages_bytes",
                "pages_entries",
                "pages_storage_max_bytes",
                "message_count",
                "message_retention_days",
                "log_bytes",
                "log_max_bytes",
                "page_cache_bytes",
                "page_cache_max_bytes",
            ):
                assert key in body, key
            assert body["attachment_storage_max_bytes"] == 512 * 1024 * 1024
            assert body["shared_storage_max_bytes"] == 1024 * 1024 * 1024
            assert body["pages_storage_max_bytes"] == 256 * 1024 * 1024
            assert body["log_max_bytes"] == 1024 * 1024
            assert body["attachment_bytes"] == 5
            assert body["message_count"] == 2

            # -- startup rotation of real oversized logs
            assert (paths.logs_dir / "meshdeck.log.1").stat().st_size == 2 * 1024 * 1024
            assert (paths.logs_dir / "reticulum.log.1").stat().st_size == 2 * 1024 * 1024
            assert (paths.logs_dir / "meshdeck.log").is_file()

            # -- strict validation, every key, never clamping
            bad_values = ["1", 1.5, True, -1]
            for key, (_minimum, maximum) in NUMERIC_SETTINGS.items():
                for bad in (*bad_values, maximum + 1):
                    async with session.put(
                        f"{base}/api/v1/settings", headers=auth, json={key: bad}
                    ) as r:
                        assert r.status == 400, (key, bad)
                        assert (await r.json())["error"]["code"] == f"invalid_{key}"
            async with session.get(f"{base}/api/v1/settings", headers=auth) as r:
                settings = await r.json()
            assert settings["attachment_storage_max_mb"] == 512
            assert settings["shared_storage_max_mb"] == 1024
            assert settings["pages_storage_max_mb"] == 256
            assert settings["message_retention_days"] == 0
            assert settings["log_max_mb"] == 1

            # -- shared files: refused over cap, then allowed after raising it
            payload = b"x" * (2 * 1024 * 1024)

            async def upload() -> tuple[int, dict]:
                form = aiohttp.FormData()
                form.add_field("file", payload, filename="big.bin")
                async with session.post(
                    f"{base}/api/v1/shared", headers=auth, data=form
                ) as resp:
                    return resp.status, await resp.json()

            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"shared_storage_max_mb": 1},
            ) as r:
                assert r.status == 200
            status, body = await upload()
            assert status == 400 and body["error"]["code"] == "shared_storage_full"
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                assert (await r.json())["shared_bytes"] == 0

            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"shared_storage_max_mb": 10},
            ) as r:
                assert r.status == 200
            status, body = await upload()
            assert status == 201 and body["size"] == len(payload)
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                body = await r.json()
            assert body["shared_bytes"] == len(payload)
            assert body["shared_files"] == 1

            # -- hosted pages: refused over cap, then allowed after raising it
            content = "x" * (1100 * 1024)  # > 1 MiB, < the 4 MiB per-page cap
            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"pages_storage_max_mb": 1},
            ) as r:
                assert r.status == 200
            async with session.put(
                f"{base}/api/v1/pages/big.mu",
                headers=auth,
                json={"content": content},
            ) as r:
                assert r.status == 400
                assert (await r.json())["error"]["code"] == "pages_storage_full"
            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"pages_storage_max_mb": 10},
            ) as r:
                assert r.status == 200
            async with session.put(
                f"{base}/api/v1/pages/big.mu",
                headers=auth,
                json={"content": content},
            ) as r:
                assert r.status == 200
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                body = await r.json()
            assert body["pages_bytes"] == len(content.encode())
            assert body["pages_entries"] == 1

            # -- attachment tombstone: saving retention is the explicit prune
            async with session.get(
                f"{base}/api/v1/attachments/{PEER}/{ATTACH_MSG}/0", headers=auth
            ) as r:
                assert r.status == 200 and await r.read() == b"hello"
            async with session.get(
                f"{base}/api/v1/messages", headers=auth, params={"peer": PEER}
            ) as r:
                messages = {m["hash"]: m for m in await r.json()}
            assert messages[ATTACH_MSG]["attachments_available"] == [True]

            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"attachment_retention_days": 1},
            ) as r:
                assert r.status == 200
                assert (await r.json())["effects"]["attachment_removed"] == 1

            async with session.get(
                f"{base}/api/v1/attachments/{PEER}/{ATTACH_MSG}/0", headers=auth
            ) as r:
                assert r.status == 404
                assert (await r.json())["error"]["code"] == "attachment_pruned"
            async with session.get(
                f"{base}/api/v1/messages", headers=auth, params={"peer": PEER}
            ) as r:
                messages = {m["hash"]: m for m in await r.json()}
            assert messages[ATTACH_MSG]["attachments_available"] == [False]
            assert messages[ATTACH_MSG]["fields_json"] and "old.bin" in json.dumps(
                messages[ATTACH_MSG]
            )
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                assert (await r.json())["attachment_bytes"] == 0

            # -- message history retention keeps peers and recent messages
            assert OLD_MSG in messages
            async with session.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"message_retention_days": 1},
            ) as r:
                assert r.status == 200
                assert (await r.json())["effects"]["messages_pruned"] == 1
            async with session.get(
                f"{base}/api/v1/messages", headers=auth, params={"peer": PEER}
            ) as r:
                hashes = {m["hash"] for m in await r.json()}
            assert OLD_MSG not in hashes and ATTACH_MSG in hashes
            async with session.get(f"{base}/api/v1/peers", headers=auth) as r:
                assert any(p["hash"] == PEER for p in await r.json())
            async with session.get(f"{base}/api/v1/status", headers=auth) as r:
                assert (await r.json())["message_count"] == 1
    finally:
        daemon.stop()
        assert daemon.exit_code == 0, daemon.log_tail()
