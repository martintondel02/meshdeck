"""Chat attachment blobs: usage, retention and byte-cap pruning.

Inbound attachments live at ``<files>/<peer>/<msg>/<index>_<name>``. The
message row keeps the attachment metadata forever; pruning only removes the
blob, so the UI can render a tombstone instead of a broken download.

Two bounds exist (settings are validated in ``config.py``):

* ``attachment_storage_max_mb`` (default 512 MiB, 0 = unlimited) — the total
  bytes of all blobs. When over, the oldest blobs (by mtime) are removed first.
* ``attachment_retention_days`` (default 0 = keep forever) — blobs whose mtime
  is older than N days are removed.

Pruning is explicit policy, never a silent cleanup of user content: it runs at
boot, after each inbound attachment, and when the settings are saved.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


def _blob_files(files_dir: Path) -> list[Path]:
    """Every regular file under *files_dir*, never following symlinks out."""
    base = files_dir.resolve()
    if not base.is_dir():
        return []
    found: list[Path] = []
    for root, _dirs, names in os.walk(base, followlinks=False):
        for name in names:
            path = Path(root) / name
            try:
                # resolve() also rejects a symlink pointing outside the store
                if path.is_file() and path.resolve().is_relative_to(base):
                    found.append(path)
            except OSError:
                continue
    return found


def _remove_empty_dirs(files_dir: Path) -> None:
    """Drop empty peer/message directories, but never the store root itself."""
    base = files_dir.resolve()
    if not base.is_dir():
        return
    for root, _dirs, _files in os.walk(base, topdown=False, followlinks=False):
        path = Path(root)
        if path == base:
            continue
        try:
            if not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def attachment_usage(files_dir: Path) -> dict[str, int]:
    """Current blob count and total bytes (cheap directory walk)."""
    files = _blob_files(files_dir)
    return {
        "attachment_files": len(files),
        "attachment_bytes": sum(_size(p) for p in files),
    }


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def prune_attachments(
    files_dir: Path,
    *,
    max_bytes: int = 0,
    retention_days: int = 0,
    now: float | None = None,
) -> dict[str, int]:
    """Apply the age policy, then the byte cap; returns what was removed.

    Message rows are never touched: only blobs, then empty directories. A blob
    newer than ``retention_days`` can still be evicted by the byte cap (the
    oldest first), so a single attachment larger than the cap is removed rather
    than silently exceeding it.
    """
    now = time.time() if now is None else now
    max_bytes = max(0, int(max_bytes))
    retention_days = max(0, int(retention_days))
    cutoff = now - retention_days * 86400 if retention_days > 0 else None

    removed = 0
    freed = 0
    kept: list[tuple[float, Path, int]] = []
    for path in _blob_files(files_dir):
        try:
            stat = path.stat()
        except OSError:
            continue
        if cutoff is not None and stat.st_mtime < cutoff:
            try:
                path.unlink()
                removed += 1
                freed += stat.st_size
            except OSError:
                pass
            continue
        kept.append((stat.st_mtime, path, stat.st_size))

    total = sum(size for _mtime, _path, size in kept)
    evicted = 0
    if max_bytes and total > max_bytes:
        for _mtime, path, size in sorted(kept, key=lambda item: (item[0], str(item[1]))):
            if total <= max_bytes:
                break
            try:
                path.unlink()
                total -= size
                removed += 1
                evicted += 1
                freed += size
            except OSError:
                continue

    _remove_empty_dirs(files_dir)
    return {
        "attachment_removed": removed,
        "attachment_freed_bytes": freed,
        "attachment_bytes": total,
        "attachment_files": len(kept) - evicted,
    }
