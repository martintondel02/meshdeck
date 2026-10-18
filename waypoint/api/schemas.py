"""Tiny request-validation helpers (no framework, explicit is better here)."""

from __future__ import annotations

from typing import Any

from waypoint.util.hexid import is_valid_hash_hex


class BadRequest(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def require_str(data: dict[str, Any], field: str, max_len: int = 10000) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BadRequest(f"missing_{field}", f"field '{field}' must be a non-empty string")
    if len(value) > max_len:
        raise BadRequest(f"{field}_too_long", f"field '{field}' exceeds {max_len} chars")
    return value


def optional_str(data: dict[str, Any], field: str, max_len: int = 10000) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise BadRequest(f"invalid_{field}", f"field '{field}' must be a string")
    if len(value) > max_len:
        raise BadRequest(f"{field}_too_long", f"field '{field}' exceeds {max_len} chars")
    return value


def require_hash(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not is_valid_hash_hex(value):
        raise BadRequest(f"invalid_{field}", f"field '{field}' must be a 32-char hex hash")
    return value.lower()  # type: ignore[union-attr]


def optional_str_from_path(value: str | None) -> str | None:
    return value if (value and is_valid_hash_hex(value)) else None
