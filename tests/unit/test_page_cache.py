"""Page cache repo + offline/stale fallback in CoreService."""

from __future__ import annotations

import time

import pytest

from meshdeck.config import AppPaths
from meshdeck.core.service import CoreService
from meshdeck.pages.client import PageFetchError
from meshdeck.storage.db import Database
from meshdeck.storage.page_cache import DEFAULT_MAX_BYTES, MAX_CACHE_BYTES, PageCache

NODE = "ab" * 16


def test_put_get_and_overwrite(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db)
        assert cache.get(NODE, "/page/index.mu") is None
        assert cache.put(NODE, "/page/index.mu", ">first", fetched_ts=100.0)
        row = cache.get(NODE, "/page/index.mu")
        assert row and row["content"] == ">first"
        assert row["content_bytes"] == 6

        assert cache.put(NODE, "/page/index.mu", ">second", fetched_ts=200.0)
        rows = cache.list()
        assert len(rows) == 1
        assert rows[0]["fetched_ts"] == 200.0
        assert cache.get(NODE, "/page/index.mu")["content"] == ">second"


def test_size_cap_refuses_oversize_entry(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db)
        big = "x" * (MAX_CACHE_BYTES + 1)
        assert cache.put(NODE, "/page/big.mu", big) is False
        assert cache.get(NODE, "/page/big.mu") is None


def test_prune_by_age_and_row_cap(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db)
        now = time.time()
        cache.put(NODE, "/page/old.mu", "old", fetched_ts=now - 10_000)
        for i in range(5):
            cache.put(NODE, f"/page/p{i}.mu", f"p{i}", fetched_ts=now + i)

        cache.prune(older_than_seconds=1000, max_rows=3)
        rows = cache.list()
        assert len(rows) == 3
        assert {r["path"] for r in rows} == {"/page/p2.mu", "/page/p3.mu", "/page/p4.mu"}
        assert cache.get(NODE, "/page/old.mu") is None


# -- Phase 6.3: total-bytes ceiling ------------------------------------------


def test_total_bytes_and_default_cap(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db)
        assert cache.max_bytes == DEFAULT_MAX_BYTES == 64 * 1024 * 1024
        assert cache.total_bytes() == 0
        cache.put(NODE, "/page/a.mu", "12345", fetched_ts=1.0)
        cache.put(NODE, "/page/b.mu", "678", fetched_ts=2.0)
        assert cache.total_bytes() == 8
        assert cache.count() == 2


def test_byte_cap_evicts_oldest_until_new_entry_fits(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=100)
        assert cache.put(NODE, "/page/a.mu", "a" * 40, fetched_ts=1.0)
        assert cache.put(NODE, "/page/b.mu", "b" * 40, fetched_ts=2.0)
        assert cache.put(NODE, "/page/c.mu", "c" * 40, fetched_ts=3.0)
        # 120 bytes > 100: the oldest row made room for c.
        assert cache.total_bytes() <= 100
        assert cache.get(NODE, "/page/a.mu") is None
        assert cache.get(NODE, "/page/b.mu") is not None
        assert cache.get(NODE, "/page/c.mu") is not None


def test_total_stays_under_cap_across_many_puts(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=1000)
        for i in range(50):
            assert cache.put(NODE, f"/page/{i}.mu", "x" * 137, fetched_ts=float(i))
            assert cache.total_bytes() <= 1000
        assert cache.count() == 7  # 7 * 137 = 959, an 8th would be 1096
        # newest are kept
        assert cache.get(NODE, "/page/49.mu") is not None
        assert cache.get(NODE, "/page/0.mu") is None


def test_entry_larger_than_total_cap_is_refused(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=100)
        assert cache.put(NODE, "/page/fits.mu", "x" * 100, fetched_ts=1.0)
        assert cache.put(NODE, "/page/huge.mu", "y" * 101, fetched_ts=2.0) is False
        assert cache.get(NODE, "/page/huge.mu") is None
        # refusing must not evict the existing entry
        assert cache.get(NODE, "/page/fits.mu") is not None
        assert cache.total_bytes() == 100


def test_unlimited_mode_still_works(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=0)
        for i in range(20):
            assert cache.put(NODE, f"/page/{i}.mu", "x" * 10_000, fetched_ts=float(i))
        assert cache.count() == 20
        assert cache.total_bytes() == 200_000
        # per-entry cap is independent of the total cap
        assert cache.put(NODE, "/page/big.mu", "x" * (MAX_CACHE_BYTES + 1)) is False


def test_overwrite_existing_entry_does_not_double_count(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=100)
        cache.put(NODE, "/page/a.mu", "a" * 60, fetched_ts=1.0)
        cache.put(NODE, "/page/b.mu", "b" * 30, fetched_ts=2.0)
        # refresh a (60 bytes) with 80 bytes: 80 + 30 = 110 > 100, so b is out
        assert cache.put(NODE, "/page/a.mu", "a" * 80, fetched_ts=3.0)
        assert cache.get(NODE, "/page/a.mu") is not None
        assert cache.get(NODE, "/page/b.mu") is None
        assert cache.total_bytes() == 80


def test_set_max_bytes_shrinks_immediately(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=1000)
        for i in range(5):
            cache.put(NODE, f"/page/{i}.mu", "x" * 100, fetched_ts=float(i))
        assert cache.total_bytes() == 500
        removed = cache.set_max_bytes(250)
        assert removed == 3
        assert cache.total_bytes() <= 250
        assert cache.get(NODE, "/page/4.mu") is not None


def test_prune_honours_byte_cap(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db, max_bytes=0)  # unlimited so puts all land
        now = time.time()
        for i in range(5):
            cache.put(NODE, f"/page/{i}.mu", "x" * 100, fetched_ts=now + i)
        assert cache.total_bytes() == 500
        cache.prune(older_than_seconds=10_000, max_rows=500, max_bytes=200)
        assert cache.total_bytes() <= 200
        assert {r["path"] for r in cache.list()} == {"/page/3.mu", "/page/4.mu"}


def test_clear_removes_every_row(tmp_path):
    with Database(tmp_path / "t.db") as db:
        cache = PageCache(db)
        cache.put(NODE, "/page/a.mu", "a")
        cache.put(NODE, "/page/b.mu", "b")
        assert cache.clear() == 2
        assert cache.count() == 0
        assert cache.total_bytes() == 0
        assert cache.clear() == 0


def _service(tmp_path) -> CoreService:
    paths = AppPaths(data_dir=tmp_path)
    paths.ensure()
    svc = CoreService(paths)
    svc.db = Database(paths.db_path)
    svc.db.open()
    svc.page_cache = PageCache(svc.db)
    return svc


async def test_fresh_cache_hit_skips_network(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    try:
        svc.page_cache.put(NODE, "/page/index.mu", ">cached")

        def boom(*_a, **_k):
            raise AssertionError("fetch_page must not run on a fresh cache hit")

        monkeypatch.setattr("meshdeck.core.service.fetch_page", boom)
        result = await svc.browse_page(NODE, "/page/index.mu")
        assert result["served_from_cache"] is True
        assert result["stale"] is False
        assert result["elapsed_ms"] == 0
        assert result["content"] == ">cached"
    finally:
        svc.db.close()


async def test_stale_cache_used_when_node_unreachable(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    try:
        old_ts = time.time() - 7200
        svc.page_cache.put(NODE, "/page/index.mu", ">saved copy", fetched_ts=old_ts)

        def no_path(*_a, **_k):
            raise PageFetchError("no_path")

        monkeypatch.setattr("meshdeck.core.service.fetch_page", no_path)
        result = await svc.browse_page(NODE, "/page/index.mu")
        assert result["served_from_cache"] is True
        assert result["stale"] is True
        assert result["error"] == "no_path"
        assert result["content"] == ">saved copy"
        assert result["cached_ts"] == old_ts
    finally:
        svc.db.close()


async def test_no_cache_means_unreachable_raises(tmp_path, monkeypatch):
    svc = _service(tmp_path)
    try:
        def no_path(*_a, **_k):
            raise PageFetchError("no_path")

        monkeypatch.setattr("meshdeck.core.service.fetch_page", no_path)
        with pytest.raises(ValueError, match="no_path"):
            await svc.browse_page(NODE, "/page/missing.mu")
    finally:
        svc.db.close()


async def test_successful_fetch_populates_cache_and_refresh_bypasses_it(
    tmp_path, monkeypatch
):
    svc = _service(tmp_path)
    try:
        calls = []

        def live(*_a, **_k):
            calls.append(1)
            return b">live page"

        monkeypatch.setattr("meshdeck.core.service.fetch_page", live)
        first = await svc.browse_page(NODE, "/page/index.mu")
        assert first["served_from_cache"] is False
        assert first["cached_ts"] is None
        assert svc.page_cache.get(NODE, "/page/index.mu")["content"] == ">live page"

        # A fresh entry is served without touching the network.
        second = await svc.browse_page(NODE, "/page/index.mu")
        assert second["served_from_cache"] is True
        assert len(calls) == 1

        # refresh=1 forces a fetch even when the entry is fresh.
        third = await svc.browse_page(NODE, "/page/index.mu", refresh=True)
        assert third["served_from_cache"] is False
        assert len(calls) == 2
    finally:
        svc.db.close()
