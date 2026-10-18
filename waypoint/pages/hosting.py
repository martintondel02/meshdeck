"""NomadNet-compatible page hosting node.

Serves micron (`.mu`) pages from the Waypoint pages directory over RNS Links,
exactly like a reference NomadNet node does: destination
("nomadnetwork", "node") + registered request handlers `/page/<path>.mu` +
"/media" placeholder. Announces carry the plain node-name bytes.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import RNS

from waypoint.core.events import EventBus
from waypoint.pages.storage import PageNameError, PageStore
from waypoint.rns.identity import IdentityManager

log = logging.getLogger(__name__)

NODE_ASPECT = "nomadnetwork.node"  # announce aspect filter (dotted)
REQUEST_PREFIX = "/page/"

default_index = """>{} — Waypoint Node

This node serves pages hosted by Waypoint.

If you are the node operator: edit `index.mu` in the app's Pages view
to replace this placeholder with your own home page.
"""


class NodeAnnounceHandler:
    """Discovers other nodes serving pages via "nomadnetwork.node" announces."""

    aspect_filter = NODE_ASPECT

    def __init__(self, bus: EventBus, own_hash_hex: str) -> None:
        self._bus = bus
        self._own = own_hash_hex

    def received_announce(self, destination_hash, announced_identity, app_data) -> None:
        try:
            hash_hex = destination_hash.hex()
            if hash_hex == self._own:
                return
            name = (
                app_data.decode("utf-8", "replace")
                if isinstance(app_data, (bytes, bytearray))
                else (str(app_data) if app_data else "")
            )
            self._bus.publish_from_thread(
                "node_announced",
                {
                    "hash": hash_hex,
                    "identity_hash": announced_identity.hash.hex(),
                    "name": name,
                    "ts": time.time(),
                },
            )
        except Exception:  # noqa: BLE001
            log.exception("node announce handling failed")


class PageHost:
    """Owns the nomadnetwork.node destination and its request handlers."""

    def __init__(
        self,
        pages_dir: Path,
        identity_manager: IdentityManager,
        bus: EventBus,
    ) -> None:
        self.store = PageStore(pages_dir)
        self._identity_manager = identity_manager
        self._bus = bus
        self._destination: RNS.Destination | None = None
        self.node_name = ""

    # -- lifecycle -----------------------------------------------------------

    def start(self, node_name: str = "") -> None:
        if self._destination is not None:
            return  # idempotent
        identity = self._identity_manager.identity
        self._destination = RNS.Destination(
            identity,
            RNS.Destination.IN,
            RNS.Destination.SINGLE,
            *NODE_ASPECT.split("."),
        )
        self.node_name = node_name or "Waypoint Node"
        self.register_all_pages()
        log.info(
            "Page hosting destination ready at %s",
            self.node_destination_hash_hex,
        )

    @property
    def node_destination_hash_hex(self) -> str:
        assert self._destination is not None
        return self._destination.hash.hex()

    def announce(self) -> None:
        assert self._destination is not None
        self._destination.announce(app_data=(self.node_name or "Waypoint Node").encode())
        log.info("Announced nomadnetwork.node destination (%s)", self.node_name)

    def set_node_name(self, name: str) -> None:
        self.node_name = name.strip() or "Waypoint Node"

    # -- page serving ----------------------------------------------------------

    def register_all_pages(self) -> None:
        """Scan the pages dir and register a handler per page (plus a default
        index placeholder if index.mu is absent)."""
        assert self._destination is not None
        names = {p["name"] for p in self.store.list_pages()}
        if "index.mu" not in names:
            self._register("/page/index.mu", default=default_index.format(self.node_name))
        for name in names:
            self._register(f"/page/{name}")

    def _register(self, request_path: str, default: str | None = None) -> None:
        assert self._destination is not None

        # Signature arity is validated by RNS: must be exactly 6 params
        # (path, data, request_id, link_id, remote_identity, requested_at).
        def generator(
            path: str,
            data: dict | None,
            request_id: Any,
            link_id: Any,
            remote_identity: Any,
            requested_at: Any,
        ) -> bytes:
            if default is not None:
                return default.encode("utf-8")
            rel = path[len(REQUEST_PREFIX):]
            try:
                content = self.store.read_bytes(rel)
            except PageNameError:
                content = None
            if content is None:
                return (
                    ">Page not found\n\nThe page you requested does not exist on this node.\n"
                ).encode("utf-8")
            return content

        self._destination.register_request_handler(
            request_path, response_generator=generator, allow=RNS.Destination.ALLOW_ALL
        )
