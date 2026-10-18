"""Token handling and hash helpers."""

import os
import stat

from meshdeck.config import load_or_create_token
from meshdeck.util.hexid import is_valid_hash_hex, short


def test_token_created_then_stable(tmp_path):
    token_path = tmp_path / "token"
    first = load_or_create_token(token_path)
    assert len(first) >= 32
    assert load_or_create_token(token_path) == first
    mode = stat.S_IMODE(os.stat(token_path).st_mode)
    assert mode == 0o600


def test_hash_validation():
    assert is_valid_hash_hex("a" * 32)
    assert is_valid_hash_hex("A1" * 16)
    assert not is_valid_hash_hex("a" * 31)
    assert not is_valid_hash_hex("zz" * 16)
    assert not is_valid_hash_hex(None)
    assert not is_valid_hash_hex(123)


def test_short_display():
    assert short("0123456789abcdef0123456789abcdef") == "01234567…cdef"
    assert short("abc") == "abc"
    assert short(None) == ""
