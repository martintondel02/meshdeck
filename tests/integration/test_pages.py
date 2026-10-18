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

PAGE = """>MeshDeck Test Node

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


def test_shared_file_download_over_link(tmp_path):
    """A hosts a shared file; B downloads it over an RNS Link and the SHA-256
    matches. Exercises the /file/<name> handlers end to end."""
    import os

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
    (dir_a / "shared").mkdir()
    payload = os.urandom(256 * 1024)
    (dir_a / "shared" / "bundle.bin").write_bytes(payload)

    proc_a = launch_node(
        dir_a,
        SERVER_EXTRA.format(port=port),
        "FileHost",
        serve_node="File Node",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT)
        node_hash_a = _read_published_hash(proc_a)
        assert node_hash_a

        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "FileReader",
            fetch_file_from=node_hash_a,
            file_name="bundle.bin",
        )
        try:
            assert wait_for_file(dir_b / "done.json", TEST_TIMEOUT), (
                "B never downloaded the shared file\n"
                + "\n".join(f"[A] {ln}" for ln in _dump(proc_a.stdout))
                + "\n"
                + "\n".join(f"[B] {ln}" for ln in _dump(proc_b.stdout))
            )
            got = json.loads((dir_b / "done.json").read_text())["fetched_file"]
            assert got["name"] == "bundle.bin"
            assert got["size"] == len(payload)
            assert got["sha256"] == hashlib.sha256(payload).hexdigest()
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)


def _read_published_hash(proc) -> str | None:
    """Read node A's stdout until the node_published event appears."""
    import select

    deadline = time.time() + BOOT_TIMEOUT
    while time.time() < deadline:
        r, _, _ = select.select([proc.stdout], [], [], 0.25)
        if r:
            line = proc.stdout.readline()
            if '"event": "node_published"' in line:
                return json.loads(line)["hash"]
    return None


def test_large_file_transfer_progress(tmp_path):
    """A hosts 8 MiB; B downloads with a transfer id and reports throttled,
    monotonic progress events ending at 1.0, then transfer_complete with the
    correct SHA-256. Total wall time must stay well under the 120 s budget."""
    import os

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
    (dir_a / "shared").mkdir()
    payload = os.urandom(8 * 1024 * 1024)
    (dir_a / "shared" / "large.bin").write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()

    proc_a = launch_node(
        dir_a,
        SERVER_EXTRA.format(port=port),
        "LargeHost",
        serve_node="Large File Node",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT)
        node_hash_a = _read_published_hash(proc_a)
        assert node_hash_a

        started = time.time()
        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "LargeReader",
            fetch_file_from=node_hash_a,
            file_name="large.bin",
            transfer_id="t-large",
        )
        try:
            assert wait_for_file(dir_b / "done.json", TEST_TIMEOUT), (
                "B never downloaded the large file\n"
                + "\n".join(f"[A] {ln}" for ln in _dump(proc_a.stdout))
                + "\n"
                + "\n".join(f"[B] {ln}" for ln in _dump(proc_b.stdout))
            )
            elapsed = time.time() - started
            result = json.loads((dir_b / "done.json").read_text())
            got = result["fetched_file"]
            assert got["size"] == len(payload)
            assert got["sha256"] == sha

            events = result["transfers"]
            # The reader retries until A's path is known; those attempts emit
            # transfer_failed(no_path) before the successful one. Anything
            # else is a real failure.
            failures = [e for e in events if e["event"] == "transfer_failed"]
            assert all(e["error"] == "no_path" for e in failures), failures
            progress = [
                e["progress"]
                for e in events
                if e["event"] == "transfer_progress" and e["id"] == "t-large"
            ]
            assert len(progress) >= 3, f"too few progress events: {progress}"
            assert progress == sorted(progress), f"progress not monotonic: {progress}"
            assert progress[-1] == 1.0, f"last progress was {progress[-1]}"
            complete = [
                e
                for e in events
                if e["event"] == "transfer_complete" and e["id"] == "t-large"
            ]
            assert len(complete) == 1
            assert complete[0]["sha256"] == sha
            assert complete[0]["bytes"] == len(payload)
            assert complete[0]["path"] == "/file/large.bin"
            assert complete[0]["elapsed_ms"] < 120_000
            assert elapsed < 120, f"transfer took {elapsed:.1f}s"
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)


def test_page_cache_serves_saved_copy_after_host_dies(tmp_path):
    """B fetches a page live, A is killed, B tries again with an expired cache
    and gets the byte-identical saved copy with stale=True instead of an error."""
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
        "CacheHost",
        serve_node="Cache Node",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT)
        node_hash_a = _read_published_hash(proc_a)
        assert node_hash_a

        trigger = dir_b / "refetch.flag"
        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "CacheReader",
            fetch_page_from=node_hash_a,
            second_fetch_trigger=str(trigger),
        )
        try:
            assert wait_for_file(dir_b / "first_fetch.json", TEST_TIMEOUT), (
                "B never fetched the page the first time"
            )
            first = json.loads((dir_b / "first_fetch.json").read_text())
            assert first["served_from_cache"] is False
            assert first["content"] == PAGE

            # Host goes away for good; expire the cache and ask again.
            proc_a.terminate()
            proc_a.wait(timeout=20)
            trigger.touch()

            assert wait_for_file(dir_b / "done.json", TEST_TIMEOUT), (
                "B never finished the offline refetch\n"
                + "\n".join(f"[B] {ln}" for ln in _dump(proc_b.stdout))
            )
            result = json.loads((dir_b / "done.json").read_text())
            second = result["refetched"]
            assert second["served_from_cache"] is True
            assert second["stale"] is True
            assert second["content"] == first["content"]
            assert second["error"] in {"no_path", "link_timeout"}
            assert second["cached_ts"] is not None
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        if proc_a.poll() is None:
            proc_a.terminate()
            proc_a.wait(timeout=20)
