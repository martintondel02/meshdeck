"""Files shared through the node destination (/file/<name> handlers).

Unlike chat attachments (which ride inside LXMF messages), these are hosted
on the node and fetched on demand over an RNS Link — the same mechanism
NomadNet nodes use, so any node browser can download them.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

MAX_SHARED_BYTES = 32 * 1024 * 1024  # matches NomadNet's auto_compress ceiling

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SharedFileError(ValueError):
    pass


class SharedStorageFull(SharedFileError):
    """New write would exceed ``shared_storage_max_mb`` (existing files stay)."""


def sanitize_shared_name(name: str) -> str:
    """Return a safe flat filename (no directories, no traversal)."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _UNSAFE.sub("_", base).lstrip("._")
    if not base:
        raise SharedFileError("empty file name")
    return base[:120]


class SharedFiles:
    def __init__(self, shared_dir: Path, max_bytes: int = 0) -> None:
        self.dir = shared_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(0, int(max_bytes))

    def set_max_bytes(self, max_bytes: int) -> int:
        """Change the total cap. Existing oversized stores are left alone."""
        self.max_bytes = max(0, int(max_bytes))
        return self.max_bytes

    def _resolve(self, name: str) -> Path:
        path = (self.dir / sanitize_shared_name(name)).resolve()
        if not path.is_relative_to(self.dir.resolve()):
            raise SharedFileError("path escapes shared dir")
        return path

    def list_files(self) -> list[dict[str, Any]]:
        out = []
        for f in sorted(self.dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                st = f.stat()
                out.append({"name": f.name, "size": st.st_size, "updated": st.st_mtime})
        return out

    def total_bytes(self) -> int:
        return sum(info["size"] for info in self.list_files())

    def count(self) -> int:
        return len(self.list_files())

    def read(self, name: str) -> bytes | None:
        f = self._resolve(name)
        return f.read_bytes() if f.is_file() else None

    def save(self, name: str, data: bytes) -> dict[str, Any]:
        if len(data) > MAX_SHARED_BYTES:
            raise SharedFileError("file is larger than 32 MiB")
        f = self._resolve(name)
        if self.max_bytes:
            used = self.total_bytes()
            if f.is_file():
                used -= f.stat().st_size  # an overwrite replaces its own bytes
            if used + len(data) > self.max_bytes:
                raise SharedStorageFull(
                    f"shared storage limit reached ({used + len(data)} > "
                    f"{self.max_bytes} bytes)"
                )
        f.write_bytes(data)
        return {"name": f.name, "size": len(data), "saved_ts": time.time()}

    def delete(self, name: str) -> None:
        f = self._resolve(name)
        if f.is_file():
            f.unlink()

