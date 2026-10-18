"""Phase 6.1 — API/route contract tests against the REAL HTTP surface.

Why this file exists
--------------------
Two user-visible bugs shipped with a green suite because the tests called
``CoreService`` directly and never exercised the aiohttp routes the UI uses:

1. ``aiohttp``'s ``{path:.+}`` capture drops the leading slash, so the UI's
   ``GET /api/v1/browse/<hash>/page/index.mu`` reached ``browse_page`` as
   ``page/index.mu``. A naive ``startswith("/page/")`` check then asked the
   node for ``/page/page/index.mu`` and every UI page fetch timed out while
   the service-level integration tests stayed green (BUILD_PLAN §14.21).
2. aiohttp matches routes in registration order, so the page catch-all
   ``/browse/{hash}/{path:.+}`` swallows ``/browse/{hash}/file/<name>`` unless
   the file route is registered first (BUILD_PLAN §14.20).

Everything here talks HTTP to a real ``python -m meshdeck`` subprocess using
its real bearer token — no in-process shortcuts.

Harness
-------
* Settings are seeded into a temp data dir's SQLite ``settings`` table before
  boot, with the same ``SettingsStore`` the daemon reads (mirrors
  ``tests/integration/node.py``).
* Two-node cases use a loopback ``TCPServerInterface`` /
  ``TCPClientInterface`` pair configured through the structured ``interfaces``
  setting, so no host network or AutoInterface IPv6 is involved.
* Ports come from the OS; ``<data>/token`` plus an authenticated
  ``GET /api/v1/status`` mark readiness. Daemons are SIGTERM'd on teardown.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import pytest

from meshdeck.config import AppPaths, SettingsStore
from meshdeck.storage.db import Database

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
BOOT_TIMEOUT = 60.0
DISCOVERY_TIMEOUT = 45.0

PAGE_CONTENT = """>Contract Page

This page is served by the node A subprocess and fetched by node B over HTTP.
"""
SHARED_PAYLOAD = b"node A shared payload \x00\x01\x02 for the browse file route\n"
ATTACHMENT_PAYLOAD = b"contract attachment payload \xde\xad\xbe\xef\n"


# ---------------------------------------------------------------------------
# process + settings harness
# ---------------------------------------------------------------------------


def free_port() -> int:
    """Ask the OS for a free loopback TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def seed_settings(data_dir: Path, **values: object) -> AppPaths:
    """Pre-seed a data dir's settings table before the daemon boots.

    Same mechanism as ``tests/integration/node.py``: the CLI's ``CoreService``
    reads these rows through ``SettingsStore`` at startup.
    """
    paths = AppPaths(data_dir=data_dir)
    paths.ensure()
    db = Database(paths.db_path)
    db.open()
    try:
        store = SettingsStore(db)
        for key, value in values.items():
            store.set(key, value)
    finally:
        db.close()
    return paths


def _sync_request(
    base: str,
    method: str,
    path: str,
    token: str | None = None,
    json_body: dict | None = None,
    timeout: float = 3.0,
) -> tuple[int, bytes]:
    """Small blocking client used only for boot/discovery polling."""
    headers: dict[str, str] = {}
    data: bytes | None = None
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        return 0, str(exc).encode()


@dataclass
class Daemon:
    """A real ``python -m meshdeck`` subprocess with its own data dir."""

    data_dir: Path
    http_port: int
    token: str = ""
    proc: subprocess.Popen | None = None
    log_path: Path = Path()
    exit_code: int | None = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.http_port}"

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def start(self) -> Daemon:
        self.log_path = self.data_dir / "daemon.log"
        log_file = self.log_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "meshdeck",
                "--data-dir",
                str(self.data_dir),
                "--port",
                str(self.http_port),
            ],
            cwd=str(REPO_ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self._log_file = log_file
        try:
            self._wait_ready()
        except BaseException:
            self.stop()
            raise
        return self

    def _wait_ready(self) -> None:
        token_path = self.data_dir / "token"
        deadline = time.monotonic() + BOOT_TIMEOUT
        last_error = "not started"
        while time.monotonic() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                raise AssertionError(
                    f"daemon exited during boot (code {self.proc.returncode})\n{self.log_tail()}"
                )
            if not self.token and token_path.exists():
                self.token = token_path.read_text(encoding="utf-8").strip()
            if self.token:
                status, raw = _sync_request(self.base, "GET", "/api/v1/status", self.token, timeout=1.0)
                if status == 200:
                    payload = json.loads(raw)
                    if payload.get("rns_running"):
                        return
                    last_error = f"status not ready: {payload}"
                else:
                    last_error = f"status HTTP {status}"
            time.sleep(0.15)
        raise AssertionError(
            f"daemon at {self.base} not ready after {BOOT_TIMEOUT}s ({last_error})\n{self.log_tail()}"
        )

    def log_tail(self, lines: int = 60) -> str:
        if not self.log_path.exists():
            return "<no daemon log>"
        return "\n".join(
            self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        )

    def stop(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()  # RNS' SIGTERM handler calls os._exit(0)
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=10)
        if self.proc is not None:
            self.exit_code = self.proc.returncode
        log_file = getattr(self, "_log_file", None)
        if log_file is not None and not log_file.closed:
            log_file.close()


@dataclass
class Pair:
    """Node A (TCP server) and node B (TCP client) over one loopback pair."""

    a: Daemon
    b: Daemon
    a_node_hash: str
    a_peer_hash: str
    b_peer_hash: str
    b_node_hash: str
    paths_a: AppPaths
    rns_port: int

    def stop(self) -> None:
        self.b.stop()
        self.a.stop()


def _wait_for_discovery(pair_a: Daemon, pair_b: Daemon, a_node: str, a_peer: str) -> None:
    """Wait until B has learned A's node destination *and* LXMF destination.

    A announces on demand (``POST /api/v1/announce``) because its first boot
    announce can fire before B's TCP client has connected.
    """
    deadline = time.monotonic() + DISCOVERY_TIMEOUT
    seen = "no announce yet"
    while time.monotonic() < deadline:
        status, _ = _sync_request(pair_a.base, "POST", "/api/v1/announce", pair_a.token)
        if status == 200:
            status, raw = _sync_request(pair_b.base, "GET", "/api/v1/nodes", pair_b.token)
            nodes = json.loads(raw) if status == 200 else []
            status, raw = _sync_request(pair_b.base, "GET", "/api/v1/peers", pair_b.token)
            peers = json.loads(raw) if status == 200 else []
            node_seen = any(node["hash"] == a_node for node in nodes)
            peer_seen = any(peer["hash"] == a_peer for peer in peers)
            seen = f"node_seen={node_seen} peer_seen={peer_seen}"
            if node_seen and peer_seen:
                return
        else:
            seen = f"announce HTTP {status}"
        time.sleep(2.0)
    raise AssertionError(
        f"B never discovered A after {DISCOVERY_TIMEOUT}s ({seen})\n"
        f"--- node A ---\n{pair_a.log_tail(30)}\n--- node B ---\n{pair_b.log_tail(30)}"
    )


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Pair:
    root = tmp_path_factory.mktemp("api-contract")
    rns_port = free_port()

    a = Daemon(root / "node_a", free_port())
    paths_a = seed_settings(
        a.data_dir,
        connect_autointerface=False,
        display_name="Node A",
        node_name="Contract Node",
        serve_pages=True,
        interfaces=[
            {
                "kind": "tcp_server",
                "name": "Contract Server",
                "enabled": True,
                "listen_ip": "127.0.0.1",
                "port": rns_port,
            }
        ],
    )
    (paths_a.pages_dir / "index.mu").write_text(PAGE_CONTENT, encoding="utf-8")
    paths_a.shared_dir.mkdir(parents=True, exist_ok=True)
    (paths_a.shared_dir / "payload.bin").write_bytes(SHARED_PAYLOAD)

    a.start()

    b = Daemon(root / "node_b", free_port())
    seed_settings(
        b.data_dir,
        connect_autointerface=False,
        display_name="Node B",
        interfaces=[
            {
                "kind": "tcp_client",
                "name": "Contract Client",
                "enabled": True,
                "target_host": "127.0.0.1",
                "target_port": rns_port,
            }
        ],
    )
    b.start()

    def identity_hash(daemon: Daemon, route: str) -> str:
        status, raw = _sync_request(daemon.base, "GET", route, daemon.token)
        assert status == 200, f"{route} failed with HTTP {status}: {raw!r}"
        return json.loads(raw)["hash"]

    a_peer = identity_hash(a, "/api/v1/identity")
    b_peer = identity_hash(b, "/api/v1/identity")
    status, raw = _sync_request(a.base, "GET", "/api/v1/node", a.token)
    assert status == 200, f"/api/v1/node failed: {status} {raw!r}"
    a_node = json.loads(raw)["node_hash"]
    status, raw = _sync_request(b.base, "GET", "/api/v1/node", b.token)
    assert status == 200, f"/api/v1/node failed: {status} {raw!r}"
    b_node = json.loads(raw)["node_hash"]

    _wait_for_discovery(a, b, a_node, a_peer)

    result = Pair(
        a=a,
        b=b,
        a_node_hash=a_node,
        a_peer_hash=a_peer,
        b_peer_hash=b_peer,
        b_node_hash=b_node,
        paths_a=paths_a,
        rns_port=rns_port,
    )
    try:
        yield result
    finally:
        result.stop()
        assert result.a.exit_code == 0, f"node A did not terminate cleanly: {result.a.exit_code}"
        assert result.b.exit_code == 0, f"node B did not terminate cleanly: {result.b.exit_code}"


# ---------------------------------------------------------------------------
# async HTTP helpers used by the tests
# ---------------------------------------------------------------------------


async def api_request(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    token: str | None,
    **kwargs: object,
) -> tuple[int, dict[str, str], bytes]:
    headers = dict(kwargs.pop("headers", {}))  # type: ignore[arg-type]
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with session.request(method, url, headers=headers, **kwargs) as response:  # type: ignore[arg-type]
        return response.status, dict(response.headers), await response.read()


async def wait_until(check, *, timeout: float, what: str, interval: float = 0.25):
    """Poll an async predicate until it returns a truthy value."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = await check()
        if last:
            return last
        await asyncio.sleep(interval)
    raise AssertionError(f"timed out after {timeout}s waiting for {what} (last={last!r})")


# ---------------------------------------------------------------------------
# 1. browse a page: the {path:.+} normalisation regression
# ---------------------------------------------------------------------------


async def test_browse_page_route_keeps_exact_node_path(pair: Pair) -> None:
    """`GET /browse/<A>/page/index.mu` must ask A for exactly `/page/index.mu`.

    This is the HTTP-level regression for ``normalize_page_path``: with the old
    naive prefix logic the route handed the client ``/page/page/index.mu`` (an
    unregistered handler), the fetch timed out and the UI saw a 400 after 25 s.
    """
    url = f"{pair.b.base}/api/v1/browse/{pair.a_node_hash}/page/index.mu"
    async with aiohttp.ClientSession() as session:
        status, _, raw = await api_request(session, "GET", url, pair.b.token)
        assert status == 200, f"browse page failed with HTTP {status}: {raw!r}"
        body = json.loads(raw)
        assert body["path"] == "/page/index.mu", (
            f"route normalisation regressed: {body['path']!r}"
        )
        assert body["content"] == PAGE_CONTENT
        assert body["served_from_cache"] is False
        assert body["stale"] is False
        assert body["node_hash"] == pair.a_node_hash

        # The cached re-read must keep the same canonical path (and not
        # re-normalise to something else).
        status, _, raw = await api_request(session, "GET", url, pair.b.token)
        assert status == 200
        cached = json.loads(raw)
        assert cached["served_from_cache"] is True
        assert cached["path"] == "/page/index.mu"


# ---------------------------------------------------------------------------
# 2. missing page: an answer, not a 500 or a 25 s hang
# ---------------------------------------------------------------------------


async def test_browse_missing_page_returns_page_not_found(pair: Pair) -> None:
    """A page whose handler is registered but whose file is gone answers 200.

    The node registers one RNS request handler per page on save (and at boot).
    Deleting a page leaves that handler in place, so a peer that knows the URL
    must get NomadNet's "Page not found" body rather than a 500 or a hang.
    This is driven through the real page API: create, delete, then browse.

    Note: a path that was *never* registered has no RNS handler at all and
    times out client-side (25 s -> 400 ``link_timeout``); that is RNS request
    routing, not this HTTP contract, and is recorded in the handoff doc.
    """
    page_url = f"{pair.a.base}/api/v1/pages/transient.mu"
    async with aiohttp.ClientSession() as session:
        status, _, raw = await api_request(
            session,
            "PUT",
            page_url,
            pair.a.token,
            json={"content": ">Transient page\n\nSaved, then deleted.\n"},
        )
        assert status == 200, f"page save failed with HTTP {status}: {raw!r}"
        status, _, raw = await api_request(session, "DELETE", page_url, pair.a.token)
        assert status == 200, f"page delete failed with HTTP {status}: {raw!r}"

        url = f"{pair.b.base}/api/v1/browse/{pair.a_node_hash}/page/transient.mu"
        started = time.monotonic()
        status, _, raw = await api_request(session, "GET", url, pair.b.token)
        elapsed = time.monotonic() - started
    assert status == 200, f"missing page returned HTTP {status}: {raw!r}"
    body = json.loads(raw)
    assert body["path"] == "/page/transient.mu"
    assert body["content"].startswith(">Page not found")
    assert elapsed < 20.0, f"missing page took {elapsed:.1f}s (looks like a link timeout)"


# ---------------------------------------------------------------------------
# 3. /browse/<hash>/file/<name> must hit the file route, not the page catch-all
# ---------------------------------------------------------------------------


async def test_browse_file_route_not_swallowed_by_page_catchall(pair: Pair) -> None:
    """Route registration order regression (BUILD_PLAN §14.20).

    If the page catch-all is registered first, ``file/payload.bin`` is treated
    as a page path, normalised to ``/page/file/payload.bin`` and times out.
    """
    url = f"{pair.b.base}/api/v1/browse/{pair.a_node_hash}/file/payload.bin"
    async with aiohttp.ClientSession() as session:
        status, headers, raw = await api_request(session, "GET", url, pair.b.token)
    assert status == 200, f"browse file failed with HTTP {status}: {raw!r}"
    assert raw == SHARED_PAYLOAD
    assert headers.get("Content-Disposition") == 'attachment; filename="payload.bin"'
    assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(SHARED_PAYLOAD).hexdigest()


# ---------------------------------------------------------------------------
# 4. /shared CRUD over real multipart HTTP
# ---------------------------------------------------------------------------


async def test_shared_upload_list_download_delete(pair: Pair) -> None:
    name = "contract-shared.txt"
    payload = b"shared through the real aiohttp multipart route\n"
    async with aiohttp.ClientSession() as session:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            payload,
            filename=name,
            content_type="application/octet-stream",
        )
        status, _, raw = await api_request(
            session, "POST", f"{pair.b.base}/api/v1/shared", pair.b.token, data=form
        )
        assert status == 201, f"upload failed with HTTP {status}: {raw!r}"
        uploaded = json.loads(raw)
        assert uploaded["name"] == name
        assert uploaded["size"] == len(payload)

        status, _, raw = await api_request(
            session, "GET", f"{pair.b.base}/api/v1/shared", pair.b.token
        )
        assert status == 200
        assert [entry["name"] for entry in json.loads(raw)] == [name]

        status, headers, raw = await api_request(
            session, "GET", f"{pair.b.base}/api/v1/shared/{name}", pair.b.token
        )
        assert status == 200
        assert raw == payload
        assert headers.get("Content-Disposition") == f'attachment; filename="{name}"'
        assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(payload).hexdigest()

        # A missing shared file is a documented client error, never a 200 with
        # an empty body and never a 500: read_shared -> ValueError("not_found")
        # -> the auth middleware maps ValueError to 400 {error.code}.
        status, _, raw = await api_request(
            session, "GET", f"{pair.b.base}/api/v1/shared/does-not-exist.bin", pair.b.token
        )
        assert status == 400, f"missing shared file returned HTTP {status}: {raw!r}"
        assert json.loads(raw)["error"]["code"] == "not_found"

        status, _, raw = await api_request(
            session, "DELETE", f"{pair.b.base}/api/v1/shared/{name}", pair.b.token
        )
        assert status == 200
        assert json.loads(raw)["deleted"] == name

        status, _, raw = await api_request(
            session, "GET", f"{pair.b.base}/api/v1/shared/{name}", pair.b.token
        )
        assert status == 400
        assert json.loads(raw)["error"]["code"] == "not_found"


# ---------------------------------------------------------------------------
# 5. attachment download after a real file message, and auth on every route
# ---------------------------------------------------------------------------


async def test_attachment_download_after_file_message(pair: Pair) -> None:
    """B sends a file message to A; A's /attachments route serves the bytes.

    The URL shape is the one the UI builds in ``attachmentUrl()``:
    ``/api/v1/attachments/<peer>/<msg>/<index>``.
    """
    async with aiohttp.ClientSession() as session:
        # Send a real LXMF attachment from B to A over the loopback pair.
        async def send_file():
            form = aiohttp.FormData()
            form.add_field("peer", pair.a_peer_hash)
            form.add_field("caption", "contract attachment")
            form.add_field(
                "file",
                ATTACHMENT_PAYLOAD,
                filename="contract-attachment.bin",
                content_type="application/octet-stream",
            )
            status, _, raw = await api_request(
                session, "POST", f"{pair.b.base}/api/v1/files", pair.b.token, data=form
            )
            if status == 202:
                return json.loads(raw)
            if status == 400 and b'"no_path"' in raw:
                return None  # the announce path has not settled yet; retry
            raise AssertionError(f"file send failed with HTTP {status}: {raw!r}")

        sent = await wait_until(send_file, timeout=30.0, what="a path for the file send")
        assert sent["state"] in ("sending", "sent", "delivered")

        # A must have persisted the inbound message with attachment metadata.
        async def inbound_message():
            status, _, raw = await api_request(
                session,
                "GET",
                f"{pair.a.base}/api/v1/messages",
                pair.a.token,
                params={"peer": pair.b_peer_hash},
            )
            if status != 200:
                return None
            for message in json.loads(raw):
                meta = json.loads(message["fields_json"] or "{}").get("attachments") or []
                if meta:
                    return message, meta[0]
            return None

        message, attachment = await wait_until(
            inbound_message, timeout=30.0, what="A to persist the inbound attachment"
        )
        assert attachment["name"] == "contract-attachment.bin"
        assert attachment["size"] == len(ATTACHMENT_PAYLOAD)

        url = (
            f"{pair.a.base}/api/v1/attachments/{pair.b_peer_hash}"
            f"/{message['hash']}/{attachment['index']}"
        )
        status, headers, raw = await api_request(session, "GET", url, pair.a.token)
        assert status == 200, f"attachment download failed with HTTP {status}: {raw!r}"
        assert raw == ATTACHMENT_PAYLOAD
        # The on-disk name is "<index>_<name>"; the route must strip the index.
        assert headers.get("Content-Disposition") == (
            'attachment; filename="contract-attachment.bin"'
        )
        assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(ATTACHMENT_PAYLOAD).hexdigest()

        # Unknown attachment -> documented 404, not a 500.
        status, _, raw = await api_request(
            session,
            "GET",
            f"{pair.a.base}/api/v1/attachments/{pair.b_peer_hash}/{message['hash']}/9",
            pair.a.token,
        )
        assert status == 404
        assert json.loads(raw)["error"]["code"] == "not_found"


async def test_new_routes_require_bearer_token(pair: Pair) -> None:
    """Every route this file touches must 401 without the bearer token."""
    node = pair.b_node_hash
    peer = pair.b_peer_hash
    msg = "ab" * 32
    routes: list[tuple[str, str]] = [
        ("GET", f"/api/v1/browse/{node}/page/index.mu"),
        ("GET", f"/api/v1/browse/{node}/file/payload.bin"),
        ("GET", "/api/v1/shared"),
        ("POST", "/api/v1/shared"),
        ("GET", "/api/v1/shared/payload.bin"),
        ("DELETE", "/api/v1/shared/payload.bin"),
        ("GET", f"/api/v1/attachments/{peer}/{msg}/0"),
        ("GET", "/api/v1/nodes"),
        ("GET", "/api/v1/propagation"),
        ("GET", "/api/v1/node"),
        ("PUT", "/api/v1/settings"),
    ]
    async with aiohttp.ClientSession() as session:
        for method, path in routes:
            status, _, raw = await api_request(
                session, method, f"{pair.b.base}{path}", None, json={}
            )
            assert status == 401, f"{method} {path} without token returned HTTP {status}: {raw!r}"
            assert json.loads(raw)["error"]["code"] == "unauthorized"


# ---------------------------------------------------------------------------
# 6. /nodes vs /node, and settings validation through the real route
# ---------------------------------------------------------------------------


async def test_nodes_and_node_agree(pair: Pair) -> None:
    """/nodes (discovered) must agree with A's own /node view; B never lists itself."""
    async with aiohttp.ClientSession() as session:
        status, _, raw = await api_request(
            session, "GET", f"{pair.a.base}/api/v1/node", pair.a.token
        )
        assert status == 200
        node_a = json.loads(raw)
        assert node_a["node_hash"] == pair.a_node_hash
        assert node_a["node_name"] == "Contract Node"
        assert node_a["serve_pages"] is True

        status, _, raw = await api_request(
            session, "GET", f"{pair.b.base}/api/v1/nodes", pair.b.token
        )
        assert status == 200
        discovered = {entry["hash"]: entry for entry in json.loads(raw)}
        assert pair.a_node_hash in discovered
        assert discovered[pair.a_node_hash]["name"] == "Contract Node"
        assert pair.b_node_hash not in discovered, "a node must not discover itself"


async def test_settings_route_rejects_invalid_delivery_method(pair: Pair) -> None:
    """The PUT route must map the service's ValueError to a 400 with a code."""
    async with aiohttp.ClientSession() as session:
        status, _, raw = await api_request(
            session,
            "PUT",
            f"{pair.b.base}/api/v1/settings",
            pair.b.token,
            json={"delivery_method": "carrier-pigeon"},
        )
        assert status == 400, f"invalid delivery_method returned HTTP {status}: {raw!r}"
        assert json.loads(raw)["error"]["code"] == "invalid_delivery_method"

        status, _, raw = await api_request(
            session,
            "PUT",
            f"{pair.b.base}/api/v1/settings",
            pair.b.token,
            json={"delivery_method": "direct"},
        )
        assert status == 200
        assert json.loads(raw)["delivery_method"] == "direct"
