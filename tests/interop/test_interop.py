"""Phase 7.4 interop: independent NomadNet / lxmd / official-lxmf binaries.

Run explicitly with the external toolchain present:

    MESHDECK_INTEROP_PYTHON=/tmp/interop/bin/python \
    MESHDECK_INTEROP_NOMADNET=/tmp/interop/bin/nomadnet \
    MESHDECK_INTEROP_LXMD=/tmp/interop/bin/lxmd \
    .venv/bin/python -m pytest tests/interop -m interop -q

Without those variables every test skips. Loopback TCP only, temp dirs,
OS-chosen ports, subprocess teardown via process groups.
"""

from __future__ import annotations

import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from meshdeck.config import AppPaths, SettingsStore
from meshdeck.storage.db import Database

pytestmark = pytest.mark.interop

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def seed(data_dir: Path, **values: object) -> AppPaths:
    paths = AppPaths(data_dir)
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


def api(base: str, path: str, token: str | None = None, method: str = "GET", body=None):
    data = None
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"null")
        except Exception:
            return exc.code, None
    except Exception:
        return 0, None


def wait_ready(base: str, token_path: Path, timeout: float = 60) -> str:
    deadline = time.time() + timeout
    token = ""
    while time.time() < deadline:
        if token_path.exists():
            token = token_path.read_text().strip()
        if token:
            status, body = api(base, "/api/v1/status", token)
            if status == 200 and body and body.get("rns_running"):
                return token
        time.sleep(0.3)
    raise AssertionError(f"daemon at {base} did not become ready")


def start_meshdeck(data_dir: Path, http_port: int) -> tuple[subprocess.Popen, Path]:
    log = (data_dir / "test-daemon.log").open("w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "meshdeck", "--data-dir", str(data_dir),
         "--port", str(http_port)],
        cwd=str(REPO), stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    return proc, log


def stop(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        return
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


def write_rns_config(path: Path, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "config").write_text(body)


def tcp_server(port: int, transport: bool = False) -> str:
    return (
        f"[reticulum]\n  enable_transport = {'Yes' if transport else 'No'}\n"
        "  share_instance = No\n[logging]\n  loglevel = 5\n"
        "[interfaces]\n  [[Loop]]\n    type = TCPServerInterface\n"
        f"    enabled = yes\n    listen_ip = 127.0.0.1\n    port = {port}\n"
    )


def tcp_client(port: int) -> str:
    return (
        "[reticulum]\n  enable_transport = No\n  share_instance = No\n"
        "[logging]\n  loglevel = 5\n[interfaces]\n  [[Loop]]\n"
        "    type = TCPClientInterface\n    enabled = yes\n"
        f"    target_host = 127.0.0.1\n    target_port = {port}\n"
    )


# ---------------------------------------------------------------------------
# Pages: real NomadNet node -> MeshDeck browse
# ---------------------------------------------------------------------------


def test_nomadnet_hosts_page_meshdeck_browses(interop, tmp_path):
    if "nomadnet" not in interop:
        pytest.skip("MESHDECK_INTEROP_NOMADNET is not set")
    nn_dir = tmp_path / "nn"
    page = ">NomadNet Interop\n\nServed by real NomadNet 1.4.4.\n"
    (nn_dir / "storage" / "pages").mkdir(parents=True)
    (nn_dir / "storage" / "pages" / "index.mu").write_text(page)
    port = free_port()
    write_rns_config(nn_dir / "rns", tcp_server(port))
    (nn_dir / "config").write_text(
        "[logging]\n  loglevel = 6\n  destination = console\n\n"
        "[client]\n  enable_client = no\n  announce_at_start = no\n\n"
        "[node]\n  enable_node = yes\n  node_name = NomadNet Interop\n"
        "  announce_at_start = Yes\n  disable_propagation = Yes\n"
    )

    data = tmp_path / "md"
    http_port = free_port()
    seed(
        data,
        connect_autointerface=False,
        display_name="MeshDeck Browser",
        interfaces=[
            {"kind": "tcp_client", "name": "NN", "enabled": True,
             "target_host": "127.0.0.1", "target_port": port}
        ],
    )
    daemon, log = start_meshdeck(data, http_port)
    time.sleep(1.0)  # let the client connect before NomadNet announces
    nn_log = (nn_dir / "nomadnet.log").open("w")
    nomadnet = subprocess.Popen(
        [str(interop["nomadnet"]), "--config", str(nn_dir),
         "--rnsconfig", str(nn_dir / "rns"), "-d", "-c"],
        stdout=nn_log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    try:
        base = f"http://127.0.0.1:{http_port}"
        token = wait_ready(base, data / "token")
        node = None
        deadline = time.time() + 45
        while time.time() < deadline:
            status, nodes = api(base, "/api/v1/nodes", token)
            if status == 200:
                node = next((n for n in nodes if n.get("name") == "NomadNet Interop"), None)
                if node:
                    break
            time.sleep(1)
        assert node is not None, "MeshDeck never discovered the NomadNet node"
        status, result = api(base, f"/api/v1/browse/{node['hash']}/page/index.mu", token)
        assert status == 200, (status, result)
        assert result["content"] == page
        assert result["served_from_cache"] is False
    finally:
        stop(nomadnet)
        stop(daemon)
        nn_log.close()
        log.close()


# ---------------------------------------------------------------------------
# LXMF: direct exchange with a standalone official-lxmf peer (both ways)
# ---------------------------------------------------------------------------


def _read_lines(proc: subprocess.Popen) -> queue.Queue:
    out: queue.Queue = queue.Queue()

    def reader() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            out.put(line.rstrip())

    threading.Thread(target=reader, daemon=True).start()
    return out


def test_official_lxmf_peer_both_directions(interop, tmp_path):
    port = free_port()
    data = tmp_path / "md"
    http_port = free_port()
    seed(
        data,
        connect_autointerface=False,
        display_name="MeshDeck LXMF",
        interfaces=[
            {"kind": "tcp_server", "name": "Loop", "enabled": True,
             "listen_ip": "127.0.0.1", "port": port}
        ],
    )
    daemon, log = start_meshdeck(data, http_port)
    peer = None
    try:
        base = f"http://127.0.0.1:{http_port}"
        token = wait_ready(base, data / "token")
        _, identity = api(base, "/api/v1/identity", token)
        a_hash = identity["hash"]
        peer = subprocess.Popen(
            [str(interop["python"]), str(HERE / "lxmf_peer.py"), str(port), a_hash],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lines = _read_lines(peer)
        ready = None
        deadline = time.time() + 60
        while time.time() < deadline and ready is None:
            try:
                msg = json.loads(lines.get(timeout=1))
            except queue.Empty:
                continue
            if msg.get("event") == "ready":
                ready = msg
        assert ready is not None, "official lxmf peer never became ready"
        peer_hash = ready["address"]

        deadline = time.time() + 60
        while time.time() < deadline:
            api(base, "/api/v1/announce", token, "POST")
            status, peers = api(base, "/api/v1/peers", token)
            if status == 200 and any(p["hash"] == peer_hash for p in peers):
                break
            time.sleep(1)
        status, _ = api(base, "/api/v1/messages", token, "POST",
                        {"peer": peer_hash, "content": "from meshdeck to lxmf"})
        assert status == 202

        received = None
        deadline = time.time() + 60
        while time.time() < deadline and received is None:
            try:
                msg = json.loads(lines.get(timeout=1))
            except queue.Empty:
                continue
            if msg.get("event") == "received":
                received = msg
        assert received and received["content"] == "from meshdeck to lxmf", received
        assert received["source"] == a_hash
        assert received["signature_valid"] is True

        inbound = None
        deadline = time.time() + 60
        while time.time() < deadline:
            status, messages = api(base, f"/api/v1/messages?peer={peer_hash}", token)
            if status == 200:
                inbound = next(
                    (m for m in messages if m.get("content") == "from lxmf to meshdeck"),
                    None,
                )
                if inbound:
                    break
            time.sleep(1)
        assert inbound and inbound["peer_hash"] == peer_hash, inbound
    finally:
        if peer is not None:
            peer.kill()
            peer.wait(timeout=10)
        stop(daemon)
        log.close()


# ---------------------------------------------------------------------------
# lxmd: independent propagation node, offline peer store-and-forward
# ---------------------------------------------------------------------------


def _pn_hash(python: Path, identity_path: Path) -> str:
    script = (
        "import RNS;"
        f"i=RNS.Identity.from_file('{identity_path}');"
        "print(RNS.Destination.hash(i,'lxmf','propagation').hex())"
    )
    return subprocess.check_output([str(python), "-c", script], text=True).strip()


def test_lxmd_propagation_store_and_forward(interop, tmp_path):
    if "lxmd" not in interop:
        pytest.skip("MESHDECK_INTEROP_LXMD is not set")
    lxmd_dir = tmp_path / "lxmd"
    (lxmd_dir / "rns").mkdir(parents=True)
    subprocess.run(
        [str(interop["python"]), "-c",
         f"import RNS; RNS.Identity().to_file('{lxmd_dir / 'identity'}')"],
        check=True,
    )
    pn_hex = _pn_hash(interop["python"], lxmd_dir / "identity")
    port = free_port()
    (lxmd_dir / "config").write_text(
        "[propagation]\nenable_node = yes\nannounce_at_start = yes\nautopeer = no\n"
        "message_storage_limit = 50\npropagation_stamp_cost_target = 13\n"
        "propagation_stamp_cost_flexibility = 0\n"
        "[lxmf]\nannounce_at_start = no\n[logging]\nloglevel = 5\n"
    )
    write_rns_config(lxmd_dir / "rns", tcp_server(port, transport=True))

    lxmd_log = (lxmd_dir / "lxmd.log").open("w")
    lxmd = subprocess.Popen(
        [str(interop["lxmd"]), "-p", "--config", str(lxmd_dir),
         "--rnsconfig", str(lxmd_dir / "rns")],
        stdout=lxmd_log, stderr=subprocess.STDOUT, start_new_session=True,
    )
    time.sleep(3)
    data = tmp_path / "md"
    http_port = free_port()
    seed(
        data,
        connect_autointerface=False,
        display_name="MeshDeck via lxmd",
        delivery_method="propagated",
        propagation_node_hash=pn_hex,
        interfaces=[
            {"kind": "tcp_client", "name": "LXMD", "enabled": True,
             "target_host": "127.0.0.1", "target_port": port}
        ],
    )
    daemon, log = start_meshdeck(data, http_port)
    c_dir = tmp_path / "c"
    c_dir.mkdir()
    try:
        base = f"http://127.0.0.1:{http_port}"
        token = wait_ready(base, data / "token")
        _, identity = api(base, "/api/v1/identity", token)
        announce = subprocess.run(
            [str(interop["python"]), str(HERE / "lxmf_offline_peer.py"),
             "announce", str(c_dir), str(port), pn_hex],
            capture_output=True, text=True, timeout=40,
        )
        c_hash = next(
            json.loads(line)["address"] for line in announce.stdout.splitlines()
            if line.startswith("{") and json.loads(line).get("event") == "announced"
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            status, peers = api(base, "/api/v1/peers", token)
            if status == 200 and any(p["hash"] == c_hash for p in peers):
                break
            time.sleep(1)
        status, _ = api(base, "/api/v1/messages", token, "POST",
                        {"peer": c_hash, "content": "propagated through real lxmd"})
        assert status == 202
        time.sleep(8)
        sync = subprocess.run(
            [str(interop["python"]), str(HERE / "lxmf_offline_peer.py"),
             "sync", str(c_dir), str(port), pn_hex],
            capture_output=True, text=True, timeout=180,
        )
        received = next(
            (json.loads(line) for line in sync.stdout.splitlines()
             if line.startswith("{") and json.loads(line).get("event") == "received"),
            None,
        )
        assert received is not None, sync.stdout + sync.stderr
        assert received["content"] == "propagated through real lxmd"
        assert received["source"] == identity["hash"]
        assert received["signature_valid"] is True
    finally:
        stop(daemon)
        stop(lxmd)
        lxmd_log.close()
        log.close()


# ---------------------------------------------------------------------------
# MeshDeck hosting: independent official-lxmf sender submits, receiver syncs
# ---------------------------------------------------------------------------


def test_meshdeck_hosting_independent_sender_receiver(interop, tmp_path):
    data = tmp_path / "md"
    port = free_port()
    http_port = free_port()
    seed(
        data,
        connect_autointerface=False,
        display_name="MeshDeck PN",
        host_propagation_node=True,
        transport_enabled=True,
        interfaces=[
            {"kind": "tcp_server", "name": "Loop", "enabled": True,
             "listen_ip": "127.0.0.1", "port": port}
        ],
    )
    daemon, log = start_meshdeck(data, http_port)
    c_dir = tmp_path / "c"
    d_dir = tmp_path / "d"
    c_dir.mkdir()
    d_dir.mkdir()
    sender = None
    try:
        base = f"http://127.0.0.1:{http_port}"
        token = wait_ready(base, data / "token")
        _, prop = api(base, "/api/v1/propagation", token)
        pn_hex = prop["propagation_node_hash"]
        announce = subprocess.run(
            [str(interop["python"]), str(HERE / "lxmf_offline_peer.py"),
             "announce", str(c_dir), str(port), pn_hex],
            capture_output=True, text=True, timeout=40,
        )
        c_hash = next(
            json.loads(line)["address"] for line in announce.stdout.splitlines()
            if line.startswith("{") and json.loads(line).get("event") == "announced"
        )
        sender = subprocess.Popen(
            [str(interop["python"]), str(HERE / "lxmf_sender.py"), str(d_dir),
             str(port), pn_hex, c_hash, "via MeshDeck PN from independent sender"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(1)
        subprocess.run(
            [str(interop["python"]), str(HERE / "lxmf_offline_peer.py"),
             "announce", str(c_dir), str(port), pn_hex],
            capture_output=True, text=True, timeout=40,
        )
        out, err = sender.communicate(timeout=90)
        events = [json.loads(line) for line in out.splitlines() if line.startswith("{")]
        assert any(e.get("event") == "delivered" for e in events), out + err
        time.sleep(2)
        _, prop2 = api(base, "/api/v1/propagation", token)
        assert prop2["stored_messages"] >= 1, prop2
        assert prop2["messages_received"] >= 1, prop2
        sync = subprocess.run(
            [str(interop["python"]), str(HERE / "lxmf_offline_peer.py"),
             "sync", str(c_dir), str(port), pn_hex],
            capture_output=True, text=True, timeout=180,
        )
        received = next(
            (json.loads(line) for line in sync.stdout.splitlines()
             if line.startswith("{") and json.loads(line).get("event") == "received"),
            None,
        )
        assert received is not None, sync.stdout + sync.stderr
        assert received["content"] == "via MeshDeck PN from independent sender"
        assert received["signature_valid"] is True
    finally:
        if sender is not None and sender.poll() is None:
            sender.kill()
        stop(daemon)
        log.close()
