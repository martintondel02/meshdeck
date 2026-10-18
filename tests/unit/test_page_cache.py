"""Page cache repo + offline/stale fallback in CoreService."""

from __future__ import annotations

import time

import pytest

from meshdeck.config import AppPaths
from meshdeck.core.service import CoreService
from meshdeck.pages.client import PageFetchError
from meshdeck.storage.db import Database
from meshdeck.storage.page_cache import MAX_CACHE_BYTES, PageCache

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
