"""Announce decoding must match LXMF's wire convention and never raise."""

import msgpack

from meshdeck.chat.peers import decode_lxmf_announce


def test_decode_standard_msgpack_announce():
    app_data = msgpack.packb([b"Alice", 8, ["compression"]])
    assert decode_lxmf_announce(app_data) == ("Alice", 8)


def test_decode_none_name_and_stamp():
    app_data = msgpack.packb([None, None, []])
    assert decode_lxmf_announce(app_data) == (None, None)


def test_decode_plain_utf8_legacy():
    assert decode_lxmf_announce("Bob".encode()) == ("Bob", None)


def test_decode_garbage_never_raises():
    assert decode_lxmf_announce(None) == (None, None)
    assert decode_lxmf_announce(b"") == (None, None)
    decode_lxmf_announce(b"\xff\xfe\x00binary")  # fallback path, no exception
