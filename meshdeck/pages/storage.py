"""Micron page file storage: name-validated CRUD under <data>/pages/."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9_/-]{0,120}\.mu$")


class PageNameError(ValueError):
    pass


class PageStorageFull(PageNameError):
    """New write would exceed ``pages_storage_max_mb`` (existing pages stay)."""


def validate_page_name(name: str) -> str:
    """Return the sanitized relative page name, or raise PageNameError."""
    cleaned = name.strip().lstrip("/")
    if not _VALID_NAME.match(cleaned):
        raise PageNameError(
            "page names must be lowercase a-z 0-9 _ - / segments ending in .mu"
        )
    return cleaned


class PageStore:
    def __init__(self, pages_dir: Path, max_bytes: int = 0) -> None:
        self.dir = pages_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max(0, int(max_bytes))

    def _resolve(self, name: str) -> Path:
        rel = validate_page_name(name)
        path = (self.dir / rel).resolve()
        if not path.resolve().is_relative_to(self.dir.resolve()):
            raise PageNameError("page path escapes the pages directory")
        return path

    def list_pages(self) -> list[dict[str, Any]]:
        result = []
        for f in sorted(self.dir.rglob("*.mu")):
            if f.is_file():
                stat = f.stat()
                result.append(
                    {
                        "name": f.relative_to(self.dir).as_posix(),
                        "size": stat.st_size,
                        "updated": stat.st_mtime,
                    }
                )
        return result

    def total_bytes(self) -> int:
        return sum(page["size"] for page in self.list_pages())

    def count(self) -> int:
        return len(self.list_pages())

    def set_max_bytes(self, max_bytes: int) -> int:
        """Change the total cap. Existing oversized stores are left alone."""
        self.max_bytes = max(0, int(max_bytes))
        return self.max_bytes

    def read(self, name: str) -> str:
        f = self._resolve(name)
        if not f.is_file():
            raise FileNotFoundError(name)
        return f.read_text(encoding="utf-8", errors="replace")

    def read_bytes(self, name: str) -> bytes | None:
        f = self._resolve(name)
        if not f.is_file():
            return None
        return f.read_bytes()

    def write(self, name: str, content: str) -> dict[str, Any]:
        encoded = content.encode("utf-8")
        if len(encoded) > 4 * 1024 * 1024:
            raise PageNameError("page is larger than 4 MiB")
        f = self._resolve(name)
        if self.max_bytes:
            used = self.total_bytes()
            if f.is_file():
                used -= f.stat().st_size  # an overwrite replaces its own bytes
            if used + len(encoded) > self.max_bytes:
                raise PageStorageFull(
                    f"pages storage limit reached ({used + len(encoded)} > "
                    f"{self.max_bytes} bytes)"
                )
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(content, encoding="utf-8")
        return {"name": f.relative_to(self.dir).as_posix(), "saved_ts": time.time()}

    def delete(self, name: str) -> None:
        f = self._resolve(name)
        if f.is_file():
            f.unlink()

