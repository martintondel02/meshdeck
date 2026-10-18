"""Phase 6.2: a persisted setting is actually applied when the daemon boots.

Each test seeds the settings store *before* CoreService.start() — through the
harness ``--set KEY=JSON`` flag, which writes the same SQLite settings table the
app itself persists — then boots one real daemon and asserts the effect, not
just the stored value.

This is the regression class behind the v0.1.0 startup bug: with
``host_propagation_node`` already true, ``set_propagation_hosting(True)``
early-returned, so ``LXMRouter.enable_propagation()`` never ran (no message
store, no handlers) while ``/status`` claimed hosting. Asserting settings or
status alone cannot catch that; the checks below use on-disk/runtime truth
(message store directory, RNS transport flag, announced destination, interface
state) wherever it exists.

Tests are subprocess-based (RNS state is process-global), hermetic (random
loopback ports, temp dirs, AutoInterface disabled) and independent.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

import pytest
from test_two_nodes import (
    BOOT_TIMEOUT,
    CLIENT_EXTRA,
    SERVER_EXTRA,
    free_port,
    launch_node,
    wait_for_file,
)

pytestmark = pytest.mark.integration

WATCH_TIMEOUT = 90


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=20)


def _dump(*labeled_procs: tuple[str, subprocess.Popen]) -> str:
    """Terminate the nodes and collect their stdout for a failure message."""
    chunks = []
    for label, proc in labeled_procs:
        _stop(proc)
        stream = proc.stdout
        output = stream.read() if stream is not None else ""
        chunks.append(f"--- {label} stdout ---\n{output}")
    return "\n".join(chunks)


def _boot_once(
    workdir: Path,
    display_name: str = "BootNode",
    sets: tuple[str, ...] | list[str] = (),
    extra_config: str = "",
    **kwargs: str,
) -> dict:
    """Boot one node on pre-seeded settings, wait for ready.json, exit 0.

    ``exit_after_ready`` keeps each single-node case to a couple of seconds;
    ready.json is written after the real CoreService.start() has returned.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    if sets:
        kwargs["set"] = ",".join(sets)
    proc = launch_node(
        workdir,
        extra_config,
        display_name,
        flags=("exit_after_ready",),
        **kwargs,
    )
    try:
        if not wait_for_file(workdir / "ready.json", BOOT_TIMEOUT):
            pytest.fail(
                f"{display_name} never became ready\n" + _dump((display_name, proc))
            )
        try:
            return_code = proc.wait(timeout=BOOT_TIMEOUT)
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"{display_name} did not exit after ready\n"
                + _dump((display_name, proc))
            )
        if return_code != 0:
            pytest.fail(
                f"{display_name} exited {return_code}\n"
                + _dump((display_name, proc))
            )
        return _read_json(workdir / "ready.json")
    finally:
        _stop(proc)


def _assert_hash_hex(value: str, label: str) -> None:
    assert isinstance(value, str) and len(value) == 32, f"{label}: {value!r}"
    int(value, 16)  # raises if not hex


def test_host_propagation_node_true_at_boot_starts_message_store(tmp_path):
    """The v0.1.0 bug signature: hosting must create <data>/lxmf/messagestore.

    Before the fix, status said propagation_hosting=True while this directory —
    created by LXMRouter.enable_propagation() — never existed."""
    data_dir = tmp_path / "node"
    ready = _boot_once(
        data_dir, "PropagationHost", sets=("host_propagation_node=true",)
    )

    assert ready["propagation_hosting"] is True
    _assert_hash_hex(ready["propagation_node_hash"], "propagation_node_hash")

    # On-disk truth: enable_propagation() sets storagepath+"/messagestore".
    # LXMF 1.2.1 appends "/lxmf" to the storagepath MeshDeck passes
    # (<data>/lxmf), so the store lives one level deeper than the data dir name
    # suggests: <data>/lxmf/lxmf/messagestore.
    store = data_dir / "lxmf" / "lxmf" / "messagestore"
    assert store.is_dir(), (
        "host_propagation_node=true at boot reported hosting but never ran "
        f"enable_propagation(): {store} is missing"
    )


def test_serve_pages_and_node_name_at_boot_announce_node(tmp_path):
    """serve_pages + node_name at boot: /node reports them and a peer hears it."""
    port = free_port()
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    host = launch_node(
        host_dir,
        SERVER_EXTRA.format(port=port),
        "BootPageHost",
        set='serve_pages=true,node_name="Boot Page Node"',
        api_port="0",
    )
    watcher = None
    try:
        assert wait_for_file(host_dir / "ready.json", BOOT_TIMEOUT), (
            "page host never became ready\n" + _dump(("host", host))
        )
        ready = _read_json(host_dir / "ready.json")
        assert ready["serve_pages"] is True
        assert ready["node_name"] == "Boot Page Node"
        _assert_hash_hex(ready["node_hash"], "node_hash")

        # The real /node endpoint (started by the harness on an ephemeral port)
        # must report the same applied state.
        request = urllib.request.Request(
            f"http://127.0.0.1:{ready['api_port']}/api/v1/node",
            headers={"Authorization": f"Bearer {ready['api_token']}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            node = json.loads(response.read().decode("utf-8"))
        assert node["serve_pages"] is True
        assert node["node_name"] == "Boot Page Node"
        assert node["node_hash"] == ready["node_hash"]

        # Announce evidence: a second node receives the nomadnetwork.node
        # announce with our node name. Without serve_pages the destination is
        # never announced, so this proves the boot setting took effect.
        watcher_dir = tmp_path / "watcher"
        watcher_dir.mkdir()
        watcher = launch_node(
            watcher_dir,
            CLIENT_EXTRA.format(port=port),
            "BootWatcher",
            expect_node=ready["node_hash"],
            timeout=str(WATCH_TIMEOUT),
        )
        if not wait_for_file(watcher_dir / "done.json", WATCH_TIMEOUT):
            pytest.fail(
                "watcher never received the boot-time node announce\n"
                + _dump(("host", host), ("watcher", watcher))
            )
        found = _read_json(watcher_dir / "done.json")
        assert found["ok"] is True, json.dumps(found)
        assert found["node_found"]["hash"] == ready["node_hash"]
        assert found["node_found"]["name"] == "Boot Page Node"
    finally:
        _stop(watcher)
        _stop(host)


def test_delivery_method_and_propagation_node_apply_at_boot(tmp_path):
    """propagated delivery + a propagation node are live after start alone.

    No PUT /settings and no restart: the persisted values must reach both the
    settings view and the running LXMF router."""
    propagation_hash = os.urandom(16).hex()
    ready = _boot_once(
        tmp_path / "node",
        "DeliveryNode",
        sets=(
            'delivery_method="propagated"',
            f'propagation_node_hash="{propagation_hash}"',
        ),
    )

    assert ready["delivery_method"] == "propagated"
    assert ready["propagation_node_setting"] == propagation_hash
    # Runtime truth: LXMRouter.get_outbound_propagation_node() after start().
    assert ready["outbound_propagation_node"] == propagation_hash
    # status.propagation_node_hash is this node's own store-and-forward address.
    _assert_hash_hex(ready["propagation_node_hash"], "propagation_node_hash")


def test_transport_enabled_true_at_boot_enables_rns_transport(tmp_path):
    """transport_enabled=true must reach RNS, not just the status echo.

    RnsStack.transport_enabled() (and therefore /status) only reads the
    settings value, so the assertion that matters is RNS's own runtime flag."""
    data_dir = tmp_path / "node"
    ready = _boot_once(data_dir, "TransportNode", sets=("transport_enabled=true",))

    assert ready["transport_enabled"] is True
    assert ready["rns_transport_enabled"] is True

    config = (data_dir / "reticulum" / "config").read_text(encoding="utf-8")
    assert "enable_transport = Yes" in config


def test_structured_interface_online_at_boot(tmp_path):
    """A structured `interfaces` entry is rendered and online after boot."""
    port = free_port()
    interfaces = [
        {
            "kind": "tcp_server",
            "name": "Boot Server",
            "enabled": True,
            "listen_ip": "127.0.0.1",
            "port": port,
        }
    ]
    ready = _boot_once(
        tmp_path / "node",
        "InterfaceNode",
        sets=(f"interfaces={json.dumps(interfaces)}",),
    )

    matching = [
        iface for iface in ready["interfaces"] if iface["type"] == "TCPServerInterface"
    ]
    assert matching, f"no TCPServerInterface in status.interfaces: {ready['interfaces']}"
    assert any(iface["online"] for iface in matching), matching


def test_advanced_mode_persists_across_boot(tmp_path):
    """mode=advanced written once is still applied on a fresh process boot."""
    data_dir = tmp_path / "node"
    first = _boot_once(data_dir, "ModeNode", sets=('mode="advanced"',))
    assert first["mode"] == "advanced"

    # Second boot with no --set: the value must come from the persisted store.
    second = _boot_once(data_dir, "ModeNode")
    assert second["mode"] == "advanced"
