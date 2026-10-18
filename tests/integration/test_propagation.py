"""Phase 4.3 integration test: store-and-forward across an offline peer.

Node A hosts an LXMF propagation node. Node B sends a *propagated* message to
node C's address while C is not running, so A stores it. C then comes online,
syncs from A and receives the message.

B and C are seeded with public identities (the propagation node's, and C's for
B), because an offline peer cannot announce itself. That mirrors a node that was
handed an address out of band.

Failure modes this test covers (both were live bugs when it was written):
- startup hosting: `ChatRouter.start()` must actually call
  `LXMRouter.enable_propagation()`; a setter no-op left `status` reporting
  `propagation_hosting=True` while no message store or handlers existed.
- client sync: `sync_from_propagation_node()` must identify the link with the
  *local* private identity (LXMF calls `Link.identify()`); passing the
  propagation node's public identity raised "identity does not hold a private
  key" and nothing was ever downloaded.
"""

from __future__ import annotations

import json
import select
import subprocess

import pytest
from test_two_nodes import (
    BOOT_TIMEOUT,
    CLIENT_EXTRA,
    SERVER_EXTRA,
    TEST_TIMEOUT,
    free_port,
    launch_node,
    wait_for_file,
)

pytestmark = pytest.mark.integration

MESSAGE = "propagated hello from the mesh"


def _dump(*labeled_procs) -> str:
    """Collect buffered stdout from node processes for failure messages."""
    chunks = []
    for label, proc in labeled_procs:
        lines = []
        stream = proc.stdout
        if stream is not None:
            while True:
                ready, _, _ = select.select([stream], [], [], 0)
                if not ready:
                    break
                line = stream.readline()
                if not line:
                    break
                lines.append(line.strip())
        chunks.append(f"--- {label} stdout ---\n" + "\n".join(lines))
    return "\n".join(chunks)


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=20)


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_propagated_message_reaches_offline_node(tmp_path):
    port = free_port()
    dir_a = tmp_path / "node_a"
    dir_b = tmp_path / "node_b"
    dir_c = tmp_path / "node_c"
    for directory in (dir_a, dir_b, dir_c):
        directory.mkdir()

    proc_a = None
    proc_b = None
    proc_c_seed = None
    proc_c = None

    try:
        # 1. Boot C once with no interfaces just to learn its chat address and
        #    public identity, then take it offline again.
        proc_c_seed = launch_node(
            dir_c, "", "OfflineReceiver", flags=("exit_after_ready",)
        )
        try:
            assert wait_for_file(dir_c / "ready.json", BOOT_TIMEOUT), (
                "seed node C never became ready\n" + _dump(("C-seed", proc_c_seed))
            )
            c_info = _read_json(dir_c / "ready.json")
            assert proc_c_seed.wait(timeout=BOOT_TIMEOUT) == 0, (
                "seed node C did not exit cleanly\n" + _dump(("C-seed", proc_c_seed))
            )
        finally:
            _stop(proc_c_seed)
        c_hash = c_info["hash"]
        c_public_key = c_info["public_key"]
        assert len(c_hash) == 32
        assert len(c_public_key) == 128

        # 2. A hosts a propagation node (and is the network's TCP server).
        proc_a = launch_node(
            dir_a,
            SERVER_EXTRA.format(port=port),
            "PropagationHost",
            flags=("host_propagation",),
        )
        assert wait_for_file(dir_a / "ready.json", BOOT_TIMEOUT), (
            "propagation host A never became ready\n" + _dump(("A", proc_a))
        )
        a_info = _read_json(dir_a / "ready.json")
        prop_hash = a_info["propagation_node_hash"]
        assert a_info["propagation_hosting"] is True
        assert len(prop_hash) == 32
        int(prop_hash, 16)
        assert len(a_info["public_key"]) == 128
        a_public_key = a_info["public_key"]

        # 3. B sends a propagated message to C via A. C is not running, so B
        #    must not wait for its announce; it exits once A has the message.
        proc_b = launch_node(
            dir_b,
            CLIENT_EXTRA.format(port=port),
            "Sender",
            flags=("send_without_peer_wait", "exit_after_send"),
            delivery_method="propagated",
            propagation_node=prop_hash,
            send_to=c_hash,
            message=MESSAGE,
            seed_peer=f"{c_hash}:{c_public_key},{prop_hash}:{a_public_key}",
            timeout="60",
        )
        try:
            assert wait_for_file(dir_b / "ready.json", BOOT_TIMEOUT), (
                "sender B never became ready\n"
                + _dump(("A", proc_a), ("B", proc_b))
            )
            try:
                b_returncode = proc_b.wait(timeout=TEST_TIMEOUT)
            except subprocess.TimeoutExpired:
                pytest.fail(
                    "B never finished sending the propagated message\n"
                    + _dump(("A", proc_a), ("B", proc_b))
                )
        finally:
            _stop(proc_b)
        assert b_returncode == 0, (
            "B failed to hand the propagated message to A\n"
            + _dump(("A", proc_a), ("B", proc_b))
        )
        b_result = _read_json(dir_b / "done.json")
        assert b_result["ok"] is True, json.dumps(b_result)
        assert b_result.get("send_state") in ("sent", "delivered")
        b_hash = _read_json(dir_b / "ready.json")["hash"]

        # A must still be hosting and must not have crashed while storing.
        assert proc_a.poll() is None, (
            "propagation host A exited prematurely\n" + _dump(("A", proc_a))
        )

        # 4. C comes back online, syncs from A and receives the stored message.
        proc_c = launch_node(
            dir_c,
            CLIENT_EXTRA.format(port=port),
            "OfflineReceiver",
            flags=("sync_retry",),
            propagation_node=prop_hash,
            seed_peer=f"{prop_hash}:{a_public_key}",
            expect=MESSAGE,
            timeout="60",
        )
        try:
            assert wait_for_file(dir_c / "done.json", TEST_TIMEOUT), (
                "C never received the propagated message\n"
                + _dump(("A", proc_a), ("C", proc_c))
            )
            c_result = _read_json(dir_c / "done.json")
        finally:
            _stop(proc_c)

        assert c_result["ok"] is True, (
            "C's done.json was not ok: " + json.dumps(c_result)
        )
        got = c_result["got"]
        assert got["content"] == MESSAGE
        assert got["peer"] == b_hash, (
            f"message came from {got['peer']}, expected B ({b_hash})"
        )
    finally:
        for proc in (proc_c, proc_c_seed, proc_b, proc_a):
            _stop(proc)
