"""Helpers for working with Reticulum hex hashes."""

from __future__ import annotations

import string

_HASH_HEX_LEN = 32  # Reticulum truncated hashes: 16 bytes -> 32 hex chars
_MSG_HEX_LEN = 64  # LXMF message hashes are SHA-256: 32 bytes -> 64 hex chars
_HEX = set(string.hexdigits.lower())


def is_valid_hash_hex(value: object, length: int = _HASH_HEX_LEN) -> bool:
    """Return True if *value* looks like a Reticulum destination/identity hash.

    ``length`` lets callers require a different fixed size, e.g. 64 for
    LXMF message hashes (full SHA-256, not the truncated 16-byte form).
    """
    if not isinstance(value, str):
        return False
    if len(value) != length:
        return False
    return all(ch in _HEX for ch in value.lower())


def is_valid_msg_hash_hex(value: object) -> bool:
    """LXMF message hashes are full SHA-256 (64 hex chars)."""
    return is_valid_hash_hex(value, length=_MSG_HEX_LEN)


def short(hex_hash: str | None, head: int = 8, tail: int = 4) -> str:
    """Render a hash for display: ``ab12cd34…wxyz``."""
    if not hex_hash:
        return ""
    if len(hex_hash) <= head + tail:
        return hex_hash
    return f"{hex_hash[:head]}…{hex_hash[-tail:]}"
