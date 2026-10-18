"""Integration test: one node hosts NomadNet-compatible pages; another node
discovers it via announce and fetches the page over an RNS Link."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_two_nodes import (
    BOOT_TIMEOUT,
    CLIENT_EXTRA,
    NODE_SCRIPT,
    SERVER_EXTRA,
    TEST_TIMEOUT,
    launch_node,
    wait_for_file,
)

pytestmark = pytest.mark.integration

PAGE = """>Waypoint Test Node

Welcome to the test node!

- index served from: test fixture
- check `1234
"""


def test_page_hosting_round_trip(tmp_path):
    port_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()

    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "pages").mkdir()
    (dir_a / "pages" / "index.mu").write_text(PAGE, encoding="utf-8")

    proc_a = launch_node(
        dir_a,
        SERVER_EXTRA.format(port=port),
        "AliceNode",
        serve_node="Alice's Test Node",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT)

        # node's destination hash: read from the node's pages hosting after boot —
        # printed in stdout "node_published" event; simplest: poll log lines.
        node_hash_a = None
        deadline = time.time() + BOOT_TIMEOUT
        while time.time() < deadline:
            time.sleep(0.25)
            try:
                proc_a.stdout.flush()
            except Exception:
                pass
            # read stdout via non-blocking: poll the file stream is awkward;
            # instead recompute: fetch via node's DB? Easiest: watch done from B
            # after fetching — get node hash from A's reticulum cache is complex;
            # use the stdout captured lines approach with select.
            import select

            r, _, _ = select.select([proc_a.stdout], [], [], 0.1)
            if r:
                line = proc_a.stdout.readline()
                if '"event": "node_published"' in line:
                    node_hash_a = json.loads(line)["hash"]
                    break
        assert node_hash_a, "node A never published its node hash"

        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "BobReader",
            fetch_page_from=node_hash_a,
            flags=(),
        )
        try:
            assert wait_for_file(dir_b / "done.json", TEST_TIMEOUT), (
                "B never fetched the page\n"
                + "\n".join(f"[A] {ln}" for ln in _dump(proc_a.stdout))
                + "\n"
                + "\n".join(f"[B] {ln}" for ln in _dump(proc_b.stdout))
            )
            result = json.loads((dir_b / "done.json").read_text())
            assert result["ok"]
            fetched = result["fetched"]
            assert fetched["content"] == PAGE
            assert fetched["path"] == "/page/index.mu"
            # hash check
            expected_sha = hashlib.sha256(PAGE.encode("utf-8")).hexdigest()
            actual_sha = hashlib.sha256(fetched["content"].encode("utf-8")).hexdigest()
            assert expected_sha == actual_sha
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)


def _dump(stream):
    if stream is None:
        return []
    import select as _s

    lines = []
    while True:
        r, _, _ = _s.select([stream], [], [], 0)
        if not r:
            break
        line = stream.readline()
        if not line:
            break
        lines.append(line.strip())
    return lines


def test_node_discovery_by_announce(tmp_path):
    """A serves; B (with --expect-node) sees A's nomadnetwork.node announce."""
    port_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    port_socket.bind(("127.0.0.1", 0))
    port = port_socket.getsockname()[1]
    port_socket.close()

    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()
    (dir_a / "pages").mkdir()
    (dir_a / "pages" / "index.mu").write_text(PAGE, encoding="utf-8")

    proc_a = launch_node(
        dir_a,
        SERVER_EXTRA.format(port=port),
        "AnnounceHost",
        serve_node="Announcer Node",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT)
        # grab A's node hash from stdout
        import select

        node_hash_a = None
        deadline = time.time() + BOOT_TIMEOUT
        while time.time() < deadline:
            r, _, _ = select.select([proc_a.stdout], [], [], 0.25)
            if r:
                line = proc_a.stdout.readline()
                if '"event": "node_published"' in line:
                    node_hash_a = json.loads(line)["hash"]
                    break
            if time.time() > deadline:
                break
        assert node_hash_a

        # B just watches announces (no chat), expects the node aspect announce
        ready_b = dir_b / "ready.json"
        done_b = dir_b / "done.json"
        cmd = [
            sys.executable,
            str(NODE_SCRIPT),
            "--data-dir",
            str(dir_b),
            "--display-name",
            "Watcher",
            "--extra-config-file",
            str(_write_extra(dir_b, port)),
            "--no-autointerface",
            "--expect-node",
            node_hash_a,
            "--ready-file",
            str(ready_b),
            "--done-file",
            str(done_b),
            "--timeout",
            "120",
        ]
        proc_b = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            assert wait_for_file(done_b, TEST_TIMEOUT), (
                "B never saw the node announce"
            )
            result = json.loads(done_b.read_text())
            assert result["ok"]
            assert result["node_found"]["hash"] == node_hash_a
            assert result["node_found"]["name"] == "Announcer Node"
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)


def _write_extra(dir_b: Path, port: int) -> Path:
    f = dir_b / "extra.conf"
    f.write_text(CLIENT_EXTRA.format(port=port), encoding="utf-8")
    return f
