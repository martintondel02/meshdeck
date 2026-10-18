"""End-to-end acceptance test for Phase 1: two real processes connected over a
localhost TCP interface pair discover each other via announces and deliver an
LXMF direct message."""

from __future__ import annotations

import json
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
    listen_on = 127.0.0.1
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
    workdir: Path, extra_config: str, display_name: str, **kwargs: str
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
    for key, value in kwargs.items():
        cmd += ["--" + key.replace("_", "-"), value]
    return subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def test_two_nodes_discover_and_chat(tmp_path):
    port = free_port()
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Node A: server side, expects to receive a specific message.
    proc_a = launch_node(
        dir_a,
        SERVER_EXTRA.format(port=port),
        "Alice",
        expect="hello over reticulum",
    )
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT), "node A never became ready"
        hash_a = json.loads((dir_a / "ready.json").read_text())["hash"]

        # Node B: client side, sends a message to A once A announces.
        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "Bob",
            send_to=hash_a,
            message="hello over reticulum",
        )
        try:
            ok_a = wait_for_file(dir_a / "done.json", TEST_TIMEOUT)
            ok_b = wait_for_file(dir_b / "done.json", TEST_TIMEOUT)
            if not (ok_a and ok_b):
                out_a = proc_a.stdout.read() if proc_a.stdout else ""
                out_b = proc_b.stdout.read() if proc_b.stdout else ""
                pytest.fail(
                    f"delivery failed (a_done={ok_a}, b_done={ok_b})\n"
                    f"--- node A ---\n{out_a}\n--- node B ---\n{out_b}"
                )
            result_a = json.loads((dir_a / "done.json").read_text())
            result_b = json.loads((dir_b / "done.json").read_text())
            assert result_a["ok"] and result_a["got"]["content"] == "hello over reticulum"
            assert result_b["ok"] and result_b["delivered"]

            # The peers learned about each other and persisted to the DB.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from waypoint.config import AppPaths  # noqa: E402
            from waypoint.storage.db import Database  # noqa: E402
            from waypoint.storage.peers import list_peers  # noqa: E402

            db = Database(AppPaths(data_dir=dir_a).db_path)
            db.open()
            assert any(p["display_name"] == "Bob" for p in list_peers(db))
            db.close()
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)
