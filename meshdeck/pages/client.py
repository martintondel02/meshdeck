"""NomadNet-compatible page browser client: fetch pages from other nodes
over RNS Links (blocking; call via asyncio.to_thread from async code)."""

from __future__ import annotations

import logging
import threading
import time

import RNS

log = logging.getLogger(__name__)

NODE_ASPECT_PARTS = ("nomadnetwork", "node")

DEFAULT_TIMEOUT = 25.0
ESTABLISH_TIMEOUT = 15.0
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 32 * 1024 * 1024


class PageFetchError(Exception):
    """Machine-readable failure codes are in str(exc)."""


def fetch_path(
    node_hash_hex: str,
    path: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> bytes:
    """Blocking fetch of any node request path over an RNS Link.

    Raises PageFetchError with codes: invalid_node_hash, no_path, link_timeout,
    request_failed, response_too_large.
    """
    try:
        node_hash = bytes.fromhex(node_hash_hex)
        assert len(node_hash) == 16
    except (ValueError, AssertionError):
        raise PageFetchError("invalid_node_hash") from None

    identity = RNS.Identity.recall(node_hash)
    if identity is None:
        RNS.Transport.request_path(node_hash)
        raise PageFetchError("no_path")

    destination = RNS.Destination(
        identity, RNS.Destination.OUT, RNS.Destination.SINGLE, *NODE_ASPECT_PARTS
    )
    link = RNS.Link(destination)
    established = threading.Event()
    link.set_link_established_callback(lambda _link: established.set())
    if not established.wait(ESTABLISH_TIMEOUT):
        try:
            link.teardown()
        finally:
            raise PageFetchError("link_timeout") from None

    try:
        receipt = link.request(
            path,
            data={},
            timeout=timeout,
            max_response_size=max_response_bytes,
        )
        if receipt is False:
            raise PageFetchError("request_failed")

        deadline = time.time() + timeout
        while not receipt.concluded():
            if time.time() > deadline:
                link.teardown()
                raise PageFetchError("link_timeout")
            time.sleep(0.05)

        response = receipt.get_response()
        if response is None:
            raise PageFetchError("request_failed")
        return bytes(response)
    finally:
        try:
            link.teardown()
        except Exception:  # noqa: BLE001
            pass


def fetch_page(
    node_hash_hex: str, path: str = "/page/index.mu", timeout: float = DEFAULT_TIMEOUT
) -> bytes:
    """Blocking fetch of a page from a nomadnetwork.node destination."""
    return fetch_path(node_hash_hex, path, timeout=timeout)


def fetch_file(
    node_hash_hex: str,
    name: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Blocking download of a shared file (/file/<name>) from a node."""
    return fetch_path(
        node_hash_hex,
        f"/file/{name}",
        timeout=timeout,
        max_response_bytes=MAX_FILE_BYTES,
    )
