"""Peer discovery: decode and handle lxmf.delivery announces."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import msgpack
import RNS

from waypoint.core.events import EventBus

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredPeer:
    destination_hash: str  # hex; the "address" users see and message
    identity_hash: str  # hex
    display_name: str | None
    stamp_cost: int | None


def decode_lxmf_announce(app_data: bytes | None) -> tuple[str | None, int | None]:
    """Decode app_data from an lxmf.delivery announce.

    LXMF packs: msgpack.packb([display_name: bytes|None, stamp_cost: int|None,
    supported_functionality: list]). Older/other implementations may send a
    plain UTF-8 display name instead. Must never raise.
    """
    if not app_data:
        return None, None
    try:
        data = msgpack.unpackb(app_data)
        if isinstance(data, (list, tuple)) and data:
            name = data[0].decode("utf-8", "replace") if isinstance(data[0], bytes) else None
            stamp = data[1] if len(data) > 1 and isinstance(data[1], int) else None
            return name, stamp
    except Exception:  # noqa: BLE001
        pass
    try:
        return app_data.decode("utf-8", "replace"), None
    except Exception:  # noqa: BLE001
        return None, None


class LxmfPeerAnnounceHandler:
    """RNS announce handler for lxmf.delivery destinations.

    Interface required by RNS.Transport.register_announce_handler:
    an `aspect_filter` attribute and a `received_announce(...)` callable.
    """

    aspect_filter = "lxmf.delivery"
    receive_path_responses = False

    def __init__(self, bus: EventBus, own_destination_hash_hex: str | None = None) -> None:
        self._bus = bus
        self._own_hash_hex = own_destination_hash_hex

    def set_own_destination_hash(self, hash_hex: str) -> None:
        """Set once our delivery destination exists (so we skip our own announces)."""
        self._own_hash_hex = hash_hex

    def received_announce(
        self,
        destination_hash: bytes,
        announced_identity: RNS.Identity,
        app_data: bytes | None,
        announce_packet_hash: bytes | None = None,
        is_path_response: bool = False,
    ) -> None:
        # Careful: runs on an RNS worker thread.
        try:
            dest_hex = destination_hash.hex()
            if self._own_hash_hex and dest_hex == self._own_hash_hex:
                return
            display_name, stamp_cost = decode_lxmf_announce(app_data)
            peer = DiscoveredPeer(
                destination_hash=dest_hex,
                identity_hash=announced_identity.hash.hex(),
                display_name=display_name,
                stamp_cost=stamp_cost,
            )
            self._bus.publish_from_thread("peer_announced", vars(peer))
        except Exception:  # noqa: BLE001 - never crash an RNS thread
            log.exception("failed to handle announce")
