"""Unit tests for chat router helpers (no network)."""

from waypoint.chat.router import MAX_ATTACHMENT_TOTAL_BYTES, sanitize_filename


def test_sanitize_filename_strips_paths_and_weirdness():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\evil.exe") == "evil.exe"
    assert sanitize_filename("docs%2F..%2F..%2Fevil%20name.bin") == "evil_name.bin"
    assert sanitize_filename("normal file.txt") == "normal_file.txt"
    assert sanitize_filename("") == "attachment"
    assert sanitize_filename("...") == "attachment"
    assert sanitize_filename("a" * 200) == "a" * 120
    assert sanitize_filename("emoji-🚀.png") == "emoji-_.png"


def test_attachment_cap_is_sane():
    # must stay below the router's inbound delivery limit (2,048,000 bytes)
    assert MAX_ATTACHMENT_TOTAL_BYTES < 2_048_000
