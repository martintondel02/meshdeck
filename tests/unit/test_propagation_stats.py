"""Phase 7.5: propagation-operator stats read from public LXMRouter state."""

from __future__ import annotations

import time

import pytest

from meshdeck.chat.router import ChatRouter
from meshdeck.config import AppPaths, SettingsStore
from meshdeck.core.service import CoreService
from meshdeck.storage.db import Database


class FakeDestination:
    hash = bytes.fromhex("ab" * 16)


class FakeRouter:
    def __init__(self) -> None:
        self.propagation_destination = FakeDestination()
        self.propagation_node = True
        self.propagation_node_start_time = time.time() - 125
        self.propagation_entries: dict[bytes, list] = {}
        self.client_propagation_messages_received = 7
        self.client_propagation_messages_served = 3
        self.unpeered_propagation_incoming = 2
        self.propagation_transfer_state = 3
        self.peers: dict[bytes, object] = {}
        self.message_storage_limit = 256_000_000

    def message_storage_size(self):
        return sum(entry[3] for entry in self.propagation_entries.values())


def _chat(tmp_path, hosting: bool = True) -> tuple[ChatRouter, FakeRouter]:
    chat = ChatRouter(
        tmp_path / "lxmf",
        tmp_path / "files",
        identity_manager=None,  # type: ignore[arg-type]
        bus=None,  # type: ignore[arg-type]
    )
    fake = FakeRouter()
    chat._router = fake  # type: ignore[assignment]
    chat._host_propagation_node = hosting
    return chat, fake


def test_not_hosting_shape_is_stable(tmp_path):
    chat, _fake = _chat(tmp_path, hosting=False)
    stats = chat.propagation_stats()
    assert stats["hosting"] is False
    assert stats["store_bytes"] is None
    assert stats["stored_messages"] is None
    assert stats["uptime_seconds"] is None
    assert stats["messages_received"] == 7
    assert stats["messages_served"] == 3
    assert stats["propagation_node_hash"] == "ab" * 16
    assert stats["store_limit_bytes"] == 256_000_000


def test_hosting_exposes_store_counters_uptime_and_state(tmp_path):
    chat, fake = _chat(tmp_path)
    now = time.time()
    fake.propagation_entries = {
        b"a" * 32: [b"dest", "/tmp/a", now, 100, [], [], 0],
        b"b" * 32: [b"dest", "/tmp/b", now, 250, [], [], 0],
    }
    stats = chat.propagation_stats()
    assert stats["hosting"] is True
    assert stats["store_bytes"] == 350
    assert stats["stored_messages"] == 2
    assert stats["messages_received"] == 7
    assert stats["messages_served"] == 3
    assert stats["unpeered_incoming"] == 2
    assert stats["transfer_state"] == "link_established"
    assert stats["transfer_state_code"] == 3
    assert stats["uptime_seconds"] is None or stats["uptime_seconds"] >= 120


@pytest.mark.parametrize(
    ("code", "name"),
    [
        (0, "idle"),
        (1, "path_requested"),
        (2, "link_establishing"),
        (3, "link_established"),
        (4, "request_sent"),
        (5, "receiving"),
        (6, "response_received"),
        (7, "complete"),
        (0xF0, "no_path"),
        (0xF1, "link_failed"),
        (0xF2, "transfer_failed"),
        (0xF3, "no_identity"),
        (0xF4, "no_access"),
        (99, "unknown"),
    ],
)
def test_transfer_state_names(tmp_path, code, name):
    chat, fake = _chat(tmp_path)
    fake.propagation_transfer_state = code
    assert chat.propagation_stats()["transfer_state"] == name


def test_torn_entry_read_does_not_raise(tmp_path):
    chat, fake = _chat(tmp_path)

    class TornDict(dict):
        def __len__(self):
            raise RuntimeError("dictionary changed size during iteration")

    fake.propagation_entries = TornDict()
    fake.message_storage_size = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("dictionary changed size during iteration")
    )
    stats = chat.propagation_stats()
    assert stats["stored_messages"] is None
    assert stats["store_bytes"] is None
    assert stats["hosting"] is True


def test_service_shape_without_router(tmp_path):
    paths = AppPaths(data_dir=tmp_path)
    paths.ensure()
    svc = CoreService(paths)
    svc.db = Database(paths.db_path)
    svc.db.open()
    svc.settings = SettingsStore(svc.db)
    try:
        stats = svc.propagation_status()
        assert stats["hosting"] is False
        assert stats["store_bytes"] is None
        assert stats["messages_received"] == 0
        assert stats["transfer_state"] == "idle"
    finally:
        svc.db.close()
