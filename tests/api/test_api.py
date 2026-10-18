"""API acceptance test: one offline (no-interface) daemon, exercised over real
HTTP+WS with its real auth token. Marked integration because it boots RNS."""

from __future__ import annotations

import aiohttp
import pytest

from meshdeck.api.server import ApiServer
from meshdeck.config import AppPaths, SettingsStore, load_or_create_token
from meshdeck.core.service import CoreService
from meshdeck.storage.db import Database

pytestmark = pytest.mark.integration


async def test_api_endtoend(tmp_path):
    # offline node: no interfaces at all -> fully hermetic test
    paths = AppPaths(data_dir=tmp_path / "wp")
    paths.ensure()
    db = Database(paths.db_path)
    db.open()
    SettingsStore(db).set("connect_autointerface", False)
    db.close()

    service = CoreService(paths)
    await service.start()
    token = load_or_create_token(paths.token_path)
    server = ApiServer(service, token)
    await server.start("127.0.0.1", 0)
    base = f"http://127.0.0.1:{server.bound_port}"

    try:
        async with aiohttp.ClientSession() as s:
            # --- auth enforcement
            async with s.get(f"{base}/api/v1/status") as r:
                assert r.status == 401
            auth = {"Authorization": f"Bearer {token}"}

            # --- status / identity
            async with s.get(f"{base}/api/v1/status", headers=auth) as r:
                assert r.status == 200
                body = await r.json()
                assert body["rns_running"] is True
                assert body["mode"] == "basic"
                assert "version" in body
            async with s.get(f"{base}/api/v1/identity", headers=auth) as r:
                identity = (await r.json())
                assert len(identity["hash"]) == 32

            # --- settings validation
            async with s.put(
                f"{base}/api/v1/settings", headers=auth, json={"mode": "nope"}
            ) as r:
                assert r.status == 400
            async with s.put(
                f"{base}/api/v1/settings", headers=auth, json={"mode": "advanced"}
            ) as r:
                assert r.status == 200
                assert (await r.json())["mode"] == "advanced"
            async with s.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"delivery_method": "carrier-pigeon"},
            ) as r:
                assert r.status == 400
            async with s.put(
                f"{base}/api/v1/settings",
                headers=auth,
                json={"propagation_node_hash": "not-hex"},
            ) as r:
                assert r.status == 400

            # --- manual peer add (no network: unknown identity -> path requested)
            async with s.post(
                f"{base}/api/v1/peers", headers=auth, json={"hash": "zz11"}
            ) as r:
                assert r.status == 400
            peer_hash = "ab" * 16
            async with s.post(
                f"{base}/api/v1/peers", headers=auth, json={"hash": peer_hash}
            ) as r:
                assert r.status == 201
                body = await r.json()
                assert body["known"] is False and body["path_requested"] is True
            async with s.get(f"{base}/api/v1/peers", headers=auth) as r:
                assert any(p["hash"] == peer_hash for p in await r.json())
            async with s.patch(
                f"{base}/api/v1/peers/{peer_hash}", headers=auth, json={"nickname": "Testy"}
            ) as r:
                assert r.status == 200 and (await r.json())["nickname"] == "Testy"
            async with s.patch(
                f"{base}/api/v1/peers/{'cd' * 16}", headers=auth, json={"blocked": True}
            ) as r:
                assert r.status == 404

            # --- messaging validation without a path (offline node)
            async with s.post(
                f"{base}/api/v1/messages",
                headers=auth,
                json={"peer": peer_hash, "content": "hi"},
            ) as r:
                assert r.status == 400
                assert (await r.json())["error"]["code"] == "no_path"
            async with s.get(
                f"{base}/api/v1/messages", headers=auth, params={"peer": peer_hash}
            ) as r:
                assert r.status == 200 and (await r.json()) == []
            async with s.get(f"{base}/api/v1/messages", headers=auth) as r:
                assert r.status == 400  # missing peer

            # --- websocket: auth + ping + unknown cmd
            with pytest.raises(aiohttp.WSServerHandshakeError):
                await s.ws_connect(f"ws://127.0.0.1:{server.bound_port}/ws")
            async with s.ws_connect(
                f"ws://127.0.0.1:{server.bound_port}/ws?token={token}"
            ) as ws:
                first = (await ws.receive()).data
                assert "hello" in first
                await ws.send_str('{"type":"cmd","id":1,"cmd":"ping"}')
                import json as _json_mod

                ack = _json_mod.loads((await ws.receive()).data)
                assert ack["ok"] is True and ack["data"]["pong"] is True
                await ws.send_str('{"type":"cmd","id":2,"cmd":"bogus"}')
                err = _json_mod.loads((await ws.receive()).data)
                assert err["type"] == "error" and err["error"]["code"] == "unknown_cmd"

            # --- pages CRUD + node publish
            async with s.put(
                f"{base}/api/v1/pages/index.mu",
                headers=auth,
                json={"content": ">Hello World\\nThis is my node."},
            ) as r:
                assert r.status == 200
                assert (await r.json())["name"] == "index.mu"
            async with s.put(
                f"{base}/api/v1/pages/Index.MU",  # uppercase = invalid name
                headers=auth,
                json={"content": "x"},
            ) as r:
                assert r.status == 400  # invalid page name rejected
            async with s.get(f"{base}/api/v1/pages", headers=auth) as r:
                assert [p["name"] for p in await r.json()] == ["index.mu"]
            async with s.get(f"{base}/api/v1/pages/index.mu", headers=auth) as r:
                assert (await r.json())["content"].startswith(">Hello World")
            async with s.post(
                f"{base}/api/v1/node/publish",
                headers=auth,
                json={"node_name": "Test Node", "serve": True},
            ) as r:
                assert r.status == 200
                info = await r.json()
                assert info["announced"] is True
                assert len(info["node_hash"]) == 32
            async with s.get(f"{base}/api/v1/node", headers=auth) as r:
                node = await r.json()
                assert node["node_name"] == "Test Node"
                assert node["serve_pages"] is True
            async with s.get(
                f"{base}/api/v1/browse/zz/index.mu", headers=auth
            ) as r:
                assert r.status == 400  # invalid node hash

            # --- shared files: upload, list, download, delete
            form = aiohttp.FormData()
            form.add_field("file", b"shared payload 123", filename="notes.txt",
                           content_type="application/octet-stream")
            async with s.post(f"{base}/api/v1/shared", headers=auth, data=form) as r:
                assert r.status == 201
                assert (await r.json())["name"] == "notes.txt"
            async with s.get(f"{base}/api/v1/shared", headers=auth) as r:
                assert [f["name"] for f in await r.json()] == ["notes.txt"]
            async with s.get(f"{base}/api/v1/shared/notes.txt", headers=auth) as r:
                assert r.status == 200
                assert await r.read() == b"shared payload 123"
                assert "notes.txt" in r.headers["Content-Disposition"]
            async with s.get(
                f"{base}/api/v1/browse/zz/file/notes.txt", headers=auth
            ) as r:
                assert r.status == 400  # invalid node hash
                assert r.status == 400  # invalid node hash
            async with s.delete(
                f"{base}/api/v1/shared/notes.txt", headers=auth
            ) as r:
                assert r.status == 200
            async with s.get(f"{base}/api/v1/shared", headers=auth) as r:
                assert await r.json() == []
    finally:
        await server.stop()
        await service.stop()
