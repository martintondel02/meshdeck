"""Phase 6.3: disk-usage limits — settings validation and LXMF application.

The LXMF parts are tested against the installed library's real behaviour:
``LXMRouter.set_message_storage_limit`` is only touched through the official
API / public attribute, and one test pins the fact that LXMF 1.2.1 itself
culls the message store to ``message_storage_limit`` (so we never fake it).
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import LXMF
import pytest

from meshdeck.chat.router import ChatRouter
from meshdeck.config import (
    AppPaths,
    SettingsStore,
    coerce_setting_int,
)
from meshdeck.core.service import CoreService
from meshdeck.storage.db import Database
from meshdeck.storage.page_cache import PageCache

NODE = "ab" * 16


# -- settings validation -----------------------------------------------------


def test_coerce_setting_int_accepts_in_range_ints():
    assert coerce_setting_int("x", 0, 0, 10240) == 0
    assert coerce_setting_int("x", 256, 0, 10240) == 256
    assert coerce_setting_int("x", 10240, 0, 10240) == 10240


@pytest.mark.parametrize("value", [-1, 10241, 1.5, "256", None, True, False, [], {}])
def test_coerce_setting_int_rejects_non_integer_or_out_of_range(value):
    with pytest.raises(ValueError, match="invalid_x"):
        coerce_setting_int("x", value, 0, 10240)


def _service(tmp_path) -> CoreService:
    paths = AppPaths(data_dir=tmp_path)
    paths.ensure()
    svc = CoreService(paths)
    svc.db = Database(paths.db_path)
    svc.db.open()
    svc.settings = SettingsStore(svc.db)
    svc.page_cache = PageCache(svc.db, max_bytes=svc._page_cache_max_bytes())
    return svc


def test_update_settings_rejects_bad_storage_limits(tmp_path):
    svc = _service(tmp_path)
    try:
        for bad in ("256", 256.5, True, -1, 10241, None):
            with pytest.raises(ValueError, match="invalid_propagation_storage_limit_mb"):
                svc.update_settings({"propagation_storage_limit_mb": bad})
        for bad in ("64", 64.0, False, -1, 1024 * 1024 * 1024 + 1):
            with pytest.raises(ValueError, match="invalid_page_cache_max_bytes"):
                svc.update_settings({"page_cache_max_bytes": bad})
        # nothing was persisted by the rejected writes
        assert svc.settings.get("propagation_storage_limit_mb") == 256
        assert svc.settings.get("page_cache_max_bytes") == 64 * 1024 * 1024
    finally:
        svc.db.close()


async def test_update_settings_accepts_and_live_applies_limits(tmp_path):
    svc = _service(tmp_path)
    svc.bus.bind(asyncio.get_running_loop())
    try:
        svc.page_cache.put(NODE, "/page/a.mu", "x" * 300)
        result = svc.update_settings({"propagation_storage_limit_mb": 128})
        assert result["propagation_storage_limit_mb"] == 128
        assert svc.settings.get("propagation_storage_limit_mb") == 128

        # 0 = unlimited, and the page cache shrinks as soon as the cap drops
        result = svc.update_settings({"page_cache_max_bytes": 100})
        assert result["page_cache_max_bytes"] == 100
        assert svc.page_cache.total_bytes() <= 100

        result = svc.update_settings({"page_cache_max_bytes": 0})
        assert result["page_cache_max_bytes"] == 0
        assert svc.page_cache.max_bytes == 0
    finally:
        svc.db.close()


def test_status_exposes_disk_usage(tmp_path):
    svc = _service(tmp_path)
    try:
        svc.page_cache.put(NODE, "/page/a.mu", "hello")
        st = svc.status()
        assert st["page_cache_bytes"] == 5
        assert st["page_cache_entries"] == 1
        assert st["page_cache_max_bytes"] == 64 * 1024 * 1024
        assert st["propagation_storage_limit_mb"] == 256
        # no chat/router in this harness -> store size unknown, not zero
        assert st["propagation_store_bytes"] is None
        assert st["propagation_storage_limit_bytes"] == 0
    finally:
        svc.db.close()


async def test_clear_page_cache_endpoint_body(tmp_path):
    svc = _service(tmp_path)
    svc.bus.bind(asyncio.get_running_loop())
    try:
        svc.page_cache.put(NODE, "/page/a.mu", "hello")
        assert svc.clear_page_cache() == {
            "cleared": 1,
            "page_cache_bytes": 0,
            "page_cache_entries": 0,
            "page_cache_max_bytes": 64 * 1024 * 1024,
        }
    finally:
        svc.db.close()


# -- LXMF propagation message store ------------------------------------------


class FakeRouter:
    """Records what ChatRouter asks LXMF to do; mirrors 1.2.1's setter math."""

    def __init__(self) -> None:
        self.message_storage_limit: int | None = None
        self.propagation_node = False
        self.entries: dict[bytes, list] = {}
        self.calls: list[str] = []
        self.setter_calls: list[dict[str, int]] = []
        self.size_error: Exception | None = None

    def set_message_storage_limit(self, kilobytes=None, megabytes=None, gigabytes=None):
        self.setter_calls.append(
            {"kilobytes": kilobytes, "megabytes": megabytes, "gigabytes": gigabytes}
        )
        limit = 0
        if kilobytes is not None:
            limit += kilobytes * 1000
        if megabytes is not None:
            limit += megabytes * 1000 * 1000
        if gigabytes is not None:
            limit += gigabytes * 1000 * 1000 * 1000
        if limit == 0:
            # LXMF 1.2.1 raises here (int(None)); MeshDeck must not rely on it
            raise ValueError("Cannot set LXMF information storage limit to None")
        self.message_storage_limit = int(limit)

    def message_storage_size(self):
        if self.size_error is not None:
            raise self.size_error
        if not self.propagation_node:
            return None
        return sum(entry[3] for entry in self.entries.values())

    def enable_propagation(self) -> None:
        self.calls.append("enable")
        self.propagation_node = True

    def disable_propagation(self) -> None:
        self.calls.append("disable")
        self.propagation_node = False


def _router(tmp_path, limit_mb: int = 256) -> tuple[ChatRouter, FakeRouter]:
    chat = ChatRouter(
        tmp_path / "lxmf",
        tmp_path / "files",
        identity_manager=None,  # type: ignore[arg-type] - never used here
        bus=None,  # type: ignore[arg-type] - never used here
        propagation_storage_limit_mb=limit_mb,
    )
    fake = FakeRouter()
    chat._router = fake  # type: ignore[assignment]
    return chat, fake


def test_storage_limit_uses_lxmfs_official_setter(tmp_path):
    chat, fake = _router(tmp_path)
    assert chat.set_propagation_storage_limit_mb(128) == 128
    assert fake.setter_calls == [{"kilobytes": None, "megabytes": 128, "gigabytes": None}]
    assert fake.message_storage_limit == 128_000_000
    assert chat.propagation_storage_limit_mb == 128
    assert chat.propagation_storage_limit_bytes == 128_000_000


def test_storage_limit_zero_means_unlimited_via_public_attribute(tmp_path):
    chat, fake = _router(tmp_path)
    chat.set_propagation_storage_limit_mb(64)
    assert chat.propagation_storage_limit_bytes == 64_000_000

    chat.set_propagation_storage_limit_mb(0)
    # LXMF's own setter cannot express unlimited; the public attribute can.
    assert fake.message_storage_limit is None
    assert chat.propagation_storage_limit_bytes == 0
    assert len(fake.setter_calls) == 1  # the zero path never used the setter


def test_enabling_hosting_applies_limit_before_enable(tmp_path):
    chat, fake = _router(tmp_path, limit_mb=32)
    chat.set_propagation_hosting(True)
    assert fake.calls == ["enable"]
    assert fake.message_storage_limit == 32_000_000

    chat.set_propagation_hosting(False)
    assert fake.calls == ["enable", "disable"]
    # the cap survives a disable/enable cycle
    chat.set_propagation_hosting(True)
    assert fake.calls == ["enable", "disable", "enable"]
    assert fake.message_storage_limit == 32_000_000


def test_store_usage_is_none_when_not_hosting(tmp_path):
    chat, fake = _router(tmp_path)
    fake.entries[b"t" * 32] = [b"d", "/tmp/x", time.time(), 1234, [], [], 0]
    assert chat.propagation_store_bytes is None

    chat.set_propagation_hosting(True)
    assert chat.propagation_store_bytes == 1234


def test_store_usage_survives_a_torn_read(tmp_path):
    chat, fake = _router(tmp_path)
    chat.set_propagation_hosting(True)
    fake.size_error = RuntimeError("dictionary changed size during iteration")
    assert chat.propagation_store_bytes is None


def test_lxmf_121_enforces_the_limit_in_its_own_store_clean(tmp_path):
    """Pins the behaviour MeshDeck relies on, against real LXMF 1.2.1 code."""
    store = tmp_path / "messagestore"
    store.mkdir()
    entries: dict[bytes, list] = {}
    for i, size in enumerate([100, 100, 100, 100, 100]):
        transient = bytes([i]) * 32
        ts = time.time() - (5 - i)
        path = store / f"{transient.hex()}_{ts}_0"
        path.write_bytes(b"x" * size)
        entries[transient] = [b"d" * 16, str(path), ts, size, [], [], 0]

    router = object.__new__(LXMF.LXMRouter)  # no RNS instance needed for this
    router.propagation_node = True
    router.propagation_entries = entries
    router.prioritised_list = []
    router.message_storage_limit = 250

    assert router.message_storage_size() == 500
    router.clean_message_store()  # LXMF's own enforcement, called by its jobs()
    size = router.message_storage_size()
    assert size is not None and size <= 250
    assert len(router.propagation_entries) == 2
    assert sum(p.stat().st_size for p in store.iterdir()) == size


def test_lxmf_121_unlimited_setter_is_broken_which_is_why_we_bypass_it():
    router = object.__new__(LXMF.LXMRouter)
    router.message_storage_limit = None
    with pytest.raises(ValueError):
        router.set_message_storage_limit(megabytes=0)
    router.set_message_storage_limit(megabytes=256)
    assert router.message_storage_limit == 256_000_000


def test_router_default_limit_is_256_mb():
    from meshdeck.chat.router import DEFAULT_PROPAGATION_STORAGE_LIMIT_MB

    assert DEFAULT_PROPAGATION_STORAGE_LIMIT_MB == 256
    chat = ChatRouter(
        Path("unused-lxmf"),
        Path("unused-files"),
        identity_manager=None,  # type: ignore[arg-type]
        bus=None,  # type: ignore[arg-type]
    )
    assert chat.propagation_storage_limit_mb == 256


def test_message_store_dir_stays_within_budget_in_our_own_wrapper(tmp_path):
    """Sanity: enabling hosting on a fake router does not touch the disk."""
    chat, fake = _router(tmp_path)
    before = set(os.listdir(tmp_path))
    chat.set_propagation_hosting(True)
    assert set(os.listdir(tmp_path)) == before
    assert fake.propagation_node is True
