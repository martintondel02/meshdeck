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


def sanitize_shared_name(name: str) -> str:
    """Return a safe flat filename (no directories, no traversal)."""
    base = name.replace("\\", "/").split("/")[-1].strip()
    base = _UNSAFE.sub("_", base).lstrip("._")
    if not base:
        raise SharedFileError("empty file name")
    return base[:120]


class SharedFiles:
    def __init__(self, shared_dir: Path) -> None:
        self.dir = shared_dir
        self.dir.mkdir(parents=True, exist_ok=True)

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

    def read(self, name: str) -> bytes | None:
        f = self._resolve(name)
        return f.read_bytes() if f.is_file() else None

    def save(self, name: str, data: bytes) -> dict[str, Any]:
        if len(data) > MAX_SHARED_BYTES:
            raise SharedFileError("file is larger than 32 MiB")
        f = self._resolve(name)
        f.write_bytes(data)
        return {"name": f.name, "size": len(data), "saved_ts": time.time()}

    def delete(self, name: str) -> None:
        f = self._resolve(name)
        if f.is_file():
            f.unlink()
