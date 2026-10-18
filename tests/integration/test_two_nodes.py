"""End-to-end acceptance tests: two real processes connected over a localhost
TCP interface pair discover each other via announces and exchange LXMF traffic."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

NODE_SCRIPT = Path(__file__).with_name("node.py")
BOOT_TIMEOUT = 60
TEST_TIMEOUT = 180

SERVER_EXTRA = """  [[Test Server]]
    type = TCPServerInterface
    enabled = yes
    listen_ip = 127.0.0.1
    port = {port}
"""

CLIENT_EXTRA = """  [[Test Client]]
    type = TCPClientInterface
    enabled = yes
    target_host = 127.0.0.1
    target_port = {port}
"""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_file(path: Path, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.25)
    return False


def launch_node(
    workdir: Path, extra_config: str, display_name: str, flags: tuple[str, ...] = (), **kwargs: str
) -> subprocess.Popen:
    extra_file = workdir / "extra.conf"
    extra_file.write_text(extra_config, encoding="utf-8")
    cmd = [
        sys.executable,
        str(NODE_SCRIPT),
        "--data-dir",
        str(workdir),
        "--display-name",
        display_name,
        "--extra-config-file",
        str(extra_file),
        "--no-autointerface",
        "--ready-file",
        str(workdir / "ready.json"),
        "--done-file",
        str(workdir / "done.json"),
        "--timeout",
        "120",
    ]
    for flag in flags:
        cmd.append("--" + flag.replace("_", "-"))
    for key, value in kwargs.items():
        cmd += ["--" + key.replace("_", "-"), value]
    return subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def _run_pair(
    tmp_path, name_a, extra_a_kwargs, name_b, extra_b_kwargs, flags_a=(), flags_b=()
):
    """Boot node A (server) and node B (client), wait for both done conditions,
    return (result_a, result_b, dir_a, dir_b)."""
    port = free_port()
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()

    proc_a = launch_node(
        dir_a, SERVER_EXTRA.format(port=port), name_a, flags=flags_a, **extra_a_kwargs
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT), "node A never became ready"
        hash_a = json.loads((dir_a / "ready.json").read_text())["hash"]
        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            name_b,
            flags=flags_b,
            send_to=hash_a,
            **extra_b_kwargs,
        )
        try:
            ok_a = wait_for_file(dir_a / "done.json", TEST_TIMEOUT)
            ok_b = wait_for_file(dir_b / "done.json", TEST_TIMEOUT)
            result_a = json.loads((dir_a / "done.json").read_text()) if ok_a else {}
            result_b = json.loads((dir_b / "done.json").read_text()) if ok_b else {}
            if not (ok_a and ok_b):
                out_a = proc_a.stdout.read() if proc_a.stdout else ""
                out_b = proc_b.stdout.read() if proc_b.stdout else ""
                pytest.fail(
                    f"condition failed (a_done={ok_a}, b_done={ok_b})\n"
                    f"--- node A ---\n{out_a}\n--- node B ---\n{out_b}"
                )
            return result_a, result_b, dir_a, dir_b
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)


def test_reply_round_trip(tmp_path):
    """A receives 'ping' and replies 'pong'; B sends 'ping', expects 'pong'."""
    result_a, result_b, _, _ = _run_pair(
        tmp_path,
        "Alice",
        {"expect": "ping", "reply": "pong"},
        "Bob",
        {"message": "ping", "expect": "pong"},
    )
    assert result_a["ok"] and result_a["got"]["content"] == "ping"
    assert result_b["ok"] and result_b["got"]["content"] == "pong"


def test_file_transfer_1mib(tmp_path):
    """B sends a 1 MiB random file to A as an LXMF attachment; hashes must match."""
    payload_path = tmp_path / "payload.bin"
    payload_path.write_bytes(os.urandom(1024 * 1024))
    expected_sha = hashlib.sha256(payload_path.read_bytes()).hexdigest()

    result_a, result_b, dir_a, _ = _run_pair(
        tmp_path,
        "Alice",
        {},
        "Bob",
        {"send_file": str(payload_path)},
        flags_a=("expect_attachments",),
    )
    assert result_b["ok"], "B did not get a delivery receipt"
    assert result_a["ok"], "A did not receive the attachment"

    got_meta = result_a["got"]["attachments"]
    assert len(got_meta) == 1
    assert got_meta[0]["name"] == "payload.bin"
    assert got_meta[0]["size"] == 1024 * 1024
    assert got_meta[0]["sha256"] == expected_sha

    # The file is persisted under the receiver's files/ directory.
    saved = list(
        (dir_a / "files").glob(f"**/{got_meta[0]['index']}_payload.bin")
    )
    assert saved and hashlib.sha256(saved[0].read_bytes()).hexdigest() == expected_sha


def test_two_nodes_discover_and_chat(tmp_path):
    """Discovery via announces + direct LXMF delivery + DB persistence."""
    result_a, result_b, dir_a, _ = _run_pair(
        tmp_path,
        "Alice",
        {"expect": "hello over reticulum"},
        "Bob",
        {"message": "hello over reticulum"},
    )
    assert result_a["ok"] and result_a["got"]["content"] == "hello over reticulum"
    assert result_b["ok"] and result_b["delivered"]

    # The peers learned about each other and persisted to the DB.
    from waypoint.config import AppPaths
    from waypoint.storage.db import Database
    from waypoint.storage.peers import list_peers

    db = Database(AppPaths(data_dir=dir_a).db_path)
    db.open()
    assert any(p["display_name"] == "Bob" for p in list_peers(db))
    db.close()
