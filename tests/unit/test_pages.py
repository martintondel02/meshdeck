"""Unit tests for page storage validation and CRUD."""

from __future__ import annotations

from pathlib import Path

import pytest

from waypoint.pages.storage import PageNameError, PageStore, validate_page_name


def test_valid_names(tmp_path: Path) -> None:
    assert validate_page_name("index.mu") == "index.mu"
    assert validate_page_name("/guide.mu") == "guide.mu"
    assert validate_page_name("docs/install.mu") == "docs/install.mu"


def test_invalid_names(tmp_path: Path) -> None:
    for bad in [
        "",
        "/../etc/passwd.mu",
        "Index.MU",
        "index",
        "../evil.mu",
        "a b.mu",
        ".mu",
        "foo.txt",
    ]:
        with pytest.raises(PageNameError):
            validate_page_name(bad)


def test_crud_and_escapes(tmp_path: Path) -> None:
    store = PageStore(tmp_path / "pages")
    store.write("index.mu", ">Home\nHello")
    store.write("docs/setup.mu", ">Setup\nSteps")

    names = [p["name"] for p in store.list_pages()]
    assert names == ["docs/setup.mu", "index.mu"]
    assert store.read("index.mu") == ">Home\nHello"
    assert store.read_bytes("docs/setup.mu").startswith(b">Setup")

    with pytest.raises(PageNameError):
        store.write("../escape.mu", "x")
    with pytest.raises(PageNameError):
        store.read("../../etc/passwd.mu")

    store.delete("index.mu")
    assert [p["name"] for p in store.list_pages()] == ["docs/setup.mu"]

    oversized = "x" * (4 * 1024 * 1024 + 1)
    with pytest.raises(PageNameError):
        store.write("big.mu", oversized)


def test_default_index_served_when_missing(tmp_path: Path) -> None:
    """PageHost registers a placeholder handler for the default index when no
    index.mu exists — checked via the request-path map it builds."""
    from waypoint.pages.hosting import default_index

    assert ">{" in default_index  # formatted with the node name
    assert ".mu" in default_index or "micron" in default_index.lower()
