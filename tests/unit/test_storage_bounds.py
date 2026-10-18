"""Phase 7.1: bounds for attachments, shared files, pages, history and logs.

Everything here is filesystem/SQLite only (no RNS boot), except the small
``CoreService`` harness used to exercise settings validation and the status
shape. File caps are binary MiB in the settings; the stores take bytes.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from meshdeck.config import AppPaths, SettingsStore
from meshdeck.core.service import NUMERIC_SETTINGS, CoreService
from meshdeck.pages.files import SharedFiles, SharedStorageFull
from meshdeck.pages.storage import PageStorageFull, PageStore
from meshdeck.storage import messages as msg_repo
from meshdeck.storage import peers as peer_repo
from meshdeck.storage.attachments import attachment_usage, prune_attachments
from meshdeck.storage.db import Database
from meshdeck.storage.page_cache import PageCache
from meshdeck.util.logs import (
    DEFAULT_SETTINGS,
    log_usage,
    prepare_logging,
    rotate_log,
    stored_log_max_mb,
)

NODE = "ab" * 16
MSG = "cd" * 32


def _blob(files_dir: Path, peer: str, msg: str, index: int, name: str, data: bytes,
          mtime: float | None = None) -> Path:
    directory = files_dir / peer / msg
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{index}_{name}"
    path.write_bytes(data)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# -- attachments -------------------------------------------------------------


def test_attachment_usage_counts_blobs(tmp_path):
    files = tmp_path / "files"
    _blob(files, NODE, MSG, 0, "a.bin", b"12345")
    _blob(files, NODE, MSG, 1, "b.bin", b"678")
    assert attachment_usage(files) == {"attachment_files": 2, "attachment_bytes": 8}
    assert attachment_usage(tmp_path / "missing") == {
        "attachment_files": 0,
        "attachment_bytes": 0,
    }


def test_attachment_age_prune_removes_only_old_blobs(tmp_path):
    files = tmp_path / "files"
    now = time.time()
    old = _blob(files, NODE, MSG, 0, "old.bin", b"x" * 10, mtime=now - 10 * 86400)
    new = _blob(files, NODE, MSG, 1, "new.bin", b"y" * 20, mtime=now)
    result = prune_attachments(files, retention_days=5, now=now)
    assert not old.exists() and new.exists()
    assert result["attachment_removed"] == 1
    assert result["attachment_freed_bytes"] == 10
    assert result["attachment_bytes"] == 20
    assert result["attachment_files"] == 1
    # empty per-message dirs are cleaned, the file stays where it was
    assert new.parent.is_dir()


def test_attachment_byte_cap_evicts_oldest_first(tmp_path):
    files = tmp_path / "files"
    now = time.time()
    oldest = _blob(files, NODE, MSG, 0, "a.bin", b"a" * 40, mtime=now - 30)
    middle = _blob(files, NODE, MSG, 1, "b.bin", b"b" * 40, mtime=now - 20)
    newest = _blob(files, NODE, MSG, 2, "c.bin", b"c" * 40, mtime=now - 10)
    result = prune_attachments(files, max_bytes=100, now=now)
    assert not oldest.exists()
    assert middle.exists() and newest.exists()
    assert result["attachment_bytes"] == 80
    assert result["attachment_files"] == 2


def test_attachment_prune_is_unlimited_by_default(tmp_path):
    files = tmp_path / "files"
    now = time.time()
    _blob(files, NODE, MSG, 0, "a.bin", b"a" * 1000, mtime=now - 100 * 86400)
    result = prune_attachments(files, now=now)
    assert result["attachment_removed"] == 0
    assert result["attachment_bytes"] == 1000


def test_attachment_prune_removes_empty_peer_dirs_but_not_root(tmp_path):
    files = tmp_path / "files"
    now = time.time()
    blob = _blob(files, NODE, MSG, 0, "a.bin", b"a", mtime=now - 10 * 86400)
    prune_attachments(files, retention_days=1, now=now)
    assert not blob.exists()
    assert files.is_dir()
    assert not (files / NODE).exists()


def test_attachment_symlink_outside_store_is_ignored(tmp_path):
    files = tmp_path / "files"
    files.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    link = files / NODE / MSG / "0_link.bin"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    assert attachment_usage(files) == {"attachment_files": 0, "attachment_bytes": 0}
    prune_attachments(files, retention_days=1, now=time.time() + 10 * 86400)
    assert outside.exists()  # never delete a file outside the store


# -- node-shared files -------------------------------------------------------


def test_shared_store_refuses_new_writes_over_cap(tmp_path):
    store = SharedFiles(tmp_path / "shared", max_bytes=100)
    store.save("a.bin", b"a" * 60)
    assert store.total_bytes() == 60 and store.count() == 1
    with pytest.raises(SharedStorageFull):
        store.save("b.bin", b"b" * 60)
    # refused write leaves the store untouched
    assert store.total_bytes() == 60
    assert not (tmp_path / "shared" / "b.bin").exists()


def test_shared_overwrite_replaces_its_own_bytes(tmp_path):
    store = SharedFiles(tmp_path / "shared", max_bytes=100)
    store.save("a.bin", b"a" * 60)
    store.save("a.bin", b"a" * 90)  # 60 freed, 90 written
    assert store.total_bytes() == 90
    # and a shrinking overwrite needs no extra room
    store.save("a.bin", b"a" * 10)
    assert store.total_bytes() == 10


def test_existing_oversized_shared_store_only_refuses_new_writes(tmp_path):
    store = SharedFiles(tmp_path / "shared", max_bytes=100)
    (tmp_path / "shared" / "old.bin").write_bytes(b"x" * 500)  # pre-existing
    assert store.total_bytes() == 500
    with pytest.raises(SharedStorageFull):
        store.save("new.bin", b"y")
    assert (tmp_path / "shared" / "new.bin").exists() is False
    assert (tmp_path / "shared" / "old.bin").exists()  # never auto-deleted


def test_shared_zero_means_unlimited(tmp_path):
    store = SharedFiles(tmp_path / "shared", max_bytes=0)
    store.save("a.bin", b"a" * 5000)
    assert store.total_bytes() == 5000


# -- hosted pages ------------------------------------------------------------


def test_page_store_refuses_new_writes_over_cap(tmp_path):
    store = PageStore(tmp_path / "pages", max_bytes=100)
    store.write("a.mu", "a" * 60)
    with pytest.raises(PageStorageFull):
        store.write("b.mu", "b" * 60)
    assert store.total_bytes() == 60 and store.count() == 1
    assert not (tmp_path / "pages" / "b.mu").exists()


def test_page_overwrite_replaces_its_own_bytes(tmp_path):
    store = PageStore(tmp_path / "pages", max_bytes=100)
    store.write("a.mu", "a" * 60)
    store.write("a.mu", "a" * 90)
    assert store.total_bytes() == 90


def test_existing_oversized_pages_only_refuse_new_writes(tmp_path):
    store = PageStore(tmp_path / "pages", max_bytes=100)
    (tmp_path / "pages" / "old.mu").write_text("x" * 500)
    with pytest.raises(PageStorageFull):
        store.write("new.mu", "y")
    assert (tmp_path / "pages" / "old.mu").exists()
    assert not (tmp_path / "pages" / "new.mu").exists()


# -- message history ---------------------------------------------------------


def test_message_retention_keeps_peers_and_nodes(tmp_path):
    db = Database(tmp_path / "t.db")
    db.open()
    try:
        now = time.time()
        peer_repo.ensure_peer(db, NODE, "ef" * 32)
        for i, age_days in enumerate([30, 5, 1]):
            msg_repo.insert_message(
                db,
                {
                    "hash": f"{i:064x}",
                    "peer_hash": NODE,
                    "direction": msg_repo.INBOUND,
                    "state": msg_repo.RECEIVED,
                    "content": f"m{i}",
                    "created_ts": now - age_days * 86400,
                },
            )
        assert msg_repo.count_messages(db) == 3
        removed = msg_repo.prune_older_than(db, now - 7 * 86400)
        assert removed == 1
        assert msg_repo.count_messages(db) == 2
        assert peer_repo.get_peer(db, NODE) is not None
    finally:
        db.close()


# -- log rotation ------------------------------------------------------------


def _paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(data_dir=tmp_path / "data")
    paths.ensure()
    return paths


def _db_with_setting(tmp_path: Path, key: str, value: object) -> Path:
    db = Database(tmp_path / "data" / "meshdeck.db")
    db.open()
    try:
        SettingsStore(db).set(key, value)
    finally:
        db.close()
    return tmp_path / "data" / "meshdeck.db"


def test_rotate_log_keeps_one_backup(tmp_path):
    log = tmp_path / "reticulum.log"
    log.write_bytes(b"x" * 2048)
    result = rotate_log(log, 1024)
    assert result["rotated"] is True
    assert not log.exists()
    assert (tmp_path / "reticulum.log.1").stat().st_size == 2048
    # a second oversized log replaces the previous backup (one generation only)
    log.write_bytes(b"y" * 4096)
    rotate_log(log, 1024)
    assert (tmp_path / "reticulum.log.1").stat().st_size == 4096
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "reticulum.log.1"
    ]


def test_rotate_log_leaves_small_or_unlimited_files(tmp_path):
    small = tmp_path / "meshdeck.log"
    small.write_bytes(b"x" * 100)
    assert rotate_log(small, 1024)["rotated"] is False
    assert rotate_log(small, 0)["rotated"] is False
    assert small.exists()
    assert not (tmp_path / "meshdeck.log.1").exists()


def test_prepare_logging_rotates_both_managed_logs(tmp_path):
    paths = _paths(tmp_path)
    _db_with_setting(tmp_path, "log_max_mb", 1)
    for name in ("meshdeck.log", "reticulum.log"):
        (paths.logs_dir / name).write_bytes(b"x" * (1024 * 1024 + 1))
    log_path = prepare_logging(paths)
    assert log_path == paths.logs_dir / "meshdeck.log"
    for name in ("meshdeck.log", "reticulum.log"):
        assert not (paths.logs_dir / name).exists()
        assert (paths.logs_dir / f"{name}.1").stat().st_size == 1024 * 1024 + 1
    assert log_usage(paths)["log_bytes"] == 2 * (1024 * 1024 + 1)


def test_stored_log_max_mb_defaults_on_missing_or_invalid(tmp_path):
    paths = _paths(tmp_path)
    assert stored_log_max_mb(paths.db_path) == DEFAULT_SETTINGS["log_max_mb"]
    db_path = _db_with_setting(tmp_path, "log_max_mb", 3)
    assert stored_log_max_mb(db_path) == 3
    # corrupt stored value: fall back to the documented default, never crash
    db = Database(db_path)
    db.open()
    try:
        db.execute(
            "UPDATE settings SET value = ? WHERE key = 'log_max_mb'", ('"nope"',)
        )
    finally:
        db.close()
    assert stored_log_max_mb(db_path) == DEFAULT_SETTINGS["log_max_mb"]


# -- CoreService settings/validation and status ------------------------------


def _service(tmp_path: Path) -> CoreService:
    paths = AppPaths(data_dir=tmp_path)
    paths.ensure()
    svc = CoreService(paths)
    svc.db = Database(paths.db_path)
    svc.db.open()
    svc.settings = SettingsStore(svc.db)
    svc.page_cache = PageCache(svc.db, max_bytes=svc._page_cache_max_bytes())
    return svc


def test_every_numeric_setting_is_registered_with_bounds():
    assert set(NUMERIC_SETTINGS) == {
        "page_cache_max_bytes",
        "propagation_storage_limit_mb",
        "attachment_storage_max_mb",
        "attachment_retention_days",
        "shared_storage_max_mb",
        "pages_storage_max_mb",
        "message_retention_days",
        "log_max_mb",
    }
    for key, (minimum, maximum) in NUMERIC_SETTINGS.items():
        assert minimum == 0 and maximum > 0, key


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        (key, bad)
        for key in NUMERIC_SETTINGS
        for bad in ("x", 1.5, True, -1, NUMERIC_SETTINGS[key][1] + 1)
    ],
)
def test_update_settings_rejects_every_bad_numeric_value(tmp_path, key, bad):
    svc = _service(tmp_path)
    try:
        with pytest.raises(ValueError, match=f"invalid_{key}"):
            svc.update_settings({key: bad})
        assert svc.settings.get(key) == DEFAULT_SETTINGS[key]
    finally:
        svc.db.close()


async def test_update_settings_accepts_bounds_and_prunes_attachments(tmp_path):
    svc = _service(tmp_path)
    svc.bus.bind(asyncio.get_running_loop())
    now = time.time()
    old = _blob(svc.paths.files_dir, NODE, MSG, 0, "old.bin", b"x" * 10, mtime=now - 10 * 86400)
    try:
        for key, (_minimum, maximum) in NUMERIC_SETTINGS.items():
            result = svc.update_settings({key: maximum})
            assert result[key] == maximum
            result = svc.update_settings({key: 0})
            assert result[key] == 0

        svc.update_settings(
            {"attachment_storage_max_mb": 512, "attachment_retention_days": 5}
        )
        assert not old.exists()  # saving the retention is the explicit prune
        assert svc.status()["attachment_retention_days"] == 5
    finally:
        svc.db.close()


def test_status_exposes_every_usage_and_limit(tmp_path):
    svc = _service(tmp_path)
    try:
        _blob(svc.paths.files_dir, NODE, MSG, 0, "a.bin", b"12345")
        st = svc.status()
        expected = {
            "attachment_bytes": 5,
            "attachment_files": 1,
            "attachment_storage_max_bytes": 512 * 1024 * 1024,
            "attachment_retention_days": 0,
            "shared_bytes": 0,
            "shared_files": 0,
            "shared_storage_max_bytes": 1024 * 1024 * 1024,
            "pages_bytes": 0,
            "pages_entries": 0,
            "pages_storage_max_bytes": 256 * 1024 * 1024,
            "message_count": 0,
            "message_retention_days": 0,
            "log_bytes": 0,
            "log_max_bytes": 10 * 1024 * 1024,
            "page_cache_bytes": 0,
            "page_cache_max_bytes": 64 * 1024 * 1024,
        }
        for key, value in expected.items():
            assert st[key] == value, key
    finally:
        svc.db.close()


def test_attachment_known_and_availability_after_pruning(tmp_path):
    svc = _service(tmp_path)
    try:
        peer_repo.ensure_peer(svc.db, NODE, "ef" * 32)
        msg_repo.insert_message(
            svc.db,
            {
                "hash": MSG,
                "peer_hash": NODE,
                "direction": msg_repo.INBOUND,
                "state": msg_repo.RECEIVED,
                "content": "with file",
                "fields_json": json.dumps(
                    {"attachments": [{"index": 0, "name": "a.bin", "size": 3}]}
                ),
                "created_ts": time.time(),
            },
        )
        assert svc.get_attachment(NODE, MSG, 0) is None
        assert svc.attachment_known(NODE, MSG, 0) is True
        assert svc.list_messages(NODE)[0]["attachments_available"] == [False]

        blob = _blob(svc.paths.files_dir, NODE, MSG, 0, "a.bin", b"abc")
        assert svc.get_attachment(NODE, MSG, 0) == (blob, "a.bin")
        assert svc.list_messages(NODE)[0]["attachments_available"] == [True]

        blob.unlink()
        assert svc.attachment_known(NODE, MSG, 0) is True
        assert svc.list_messages(NODE)[0]["attachments_available"] == [False]
        # an unknown index and a non-inbound message are not "pruned"
        assert svc.attachment_known(NODE, MSG, 3) is False
    finally:
        svc.db.close()
