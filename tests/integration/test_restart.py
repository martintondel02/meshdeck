"""Restart/reconfigure acceptance test: changing a node's interface settings
and re-executing the process must produce connectivity on the NEW settings —
no manual config file editing, proving the wizard path end-to-end."""

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

SERVER_EXTRA = """[interfaces]
  [[Test TCP Server]]
    type = TCPServerInterface
    enabled = Yes
    listen_ip = 127.0.0.1
    port = {port}
"""

CLIENT_EXTRA = """[interfaces]
  [[Test TCP Client]]
    type = TCPClientInterface
    enabled = Yes
    target_host = 127.0.0.1
    target_port = {port}
"""


def free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def wait_for_file(path: Path, timeout: float, min_mtime: float = 0.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists() and path.stat().st_mtime > min_mtime:
            return True
        time.sleep(0.4)
    return False


def launch_a(workdir: Path, port: int, watch_file: Path) -> subprocess.Popen:
    extra = workdir / "extra.conf"
    extra.write_text(SERVER_EXTRA.format(port=port), encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            str(NODE_SCRIPT),
            "--data-dir", str(workdir),
            "--display-name", "Alice",
            "--extra-config-file", str(extra),
            "--no-autointerface",
            "--expect", "after restart",
            "--ready-file", str(workdir / "ready.json"),
            "--done-file", str(workdir / "done.json"),
            "--restart-watch-file", str(watch_file),
            "--timeout", "300",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def test_restart_applies_new_interface_config(tmp_path):
    from waypoint.config import AppPaths, SettingsStore
    from waypoint.storage.db import Database

    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_a.mkdir()
    dir_b.mkdir()
    watch_file = tmp_path / "restart.flag"

    port1 = free_port()
    proc_a = launch_a(dir_a, port1, watch_file)
    try:
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT), "node A never booted"
        boot1_mtime = (dir_a / "ready.json").stat().st_mtime
        hash_a = json.loads((dir_a / "ready.json").read_text())["hash"]

        # User edits interfaces in the wizard → settings row; then presses
        # "save & restart" → process re-exec (simulated via watch file).
        port2 = free_port()
        while port2 == port1:
            port2 = free_port()
        db = Database(AppPaths(data_dir=dir_a).db_path)
        db.open()
        SettingsStore(db).set(
            "interfaces",
            [
                {
                    "kind": "tcp_server",
                    "name": "Managed Server",
                    "enabled": True,
                    "listen_ip": "127.0.0.1",
                    "port": port2,
                }
            ],
        )
        db.close()
        # user removed the raw extra-config block in the wizard
        (dir_a / "extra.conf").write_text("[interfaces]\n", encoding="utf-8")
        watch_file.touch()  # 0 mtime-guard: file fresh, definitely newer

        # A reboots on the NEW port; ready.json rewritten.
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT, min_mtime=boot1_mtime), (
            "node A never re-booted after restart trigger"
        )

        # B connects to the NEW port and sends; only succeeds if the restart
        # applied the structured-interface settings (P1 no longer listens).
        extra_b = dir_b / "extra.conf"
        extra_b.write_text(CLIENT_EXTRA.format(port=port2), encoding="utf-8")
        proc_b = subprocess.Popen(
            [
                sys.executable, str(NODE_SCRIPT),
                "--data-dir", str(dir_b),
                "--display-name", "Bob",
                "--extra-config-file", str(extra_b),
                "--no-autointerface",
                "--send-to", hash_a,
                "--message", "after restart",
                "--ready-file", str(dir_b / "ready.json"),
                "--done-file", str(dir_b / "done.json"),
                "--timeout", "300",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            assert wait_for_file(dir_b / "done.json", TEST_TIMEOUT), (
                "B's message delivery after restart timed out"
            )
            assert wait_for_file(dir_a / "done.json", TEST_TIMEOUT), (
                "A never received the post-restart message"
            )
            result_a = json.loads((dir_a / "done.json").read_text())
            result_b = json.loads((dir_b / "done.json").read_text())
            assert result_a["ok"] and result_a["got"]["content"] == "after restart"
            assert result_b["ok"] and result_b["delivered"]
        finally:
            proc_b.terminate()
            proc_b.wait(timeout=20)
    finally:
        proc_a.terminate()
        proc_a.wait(timeout=20)
