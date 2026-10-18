"""LXMF chat router wrapper: inbound delivery handling and outbound sending."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import LXMF
import RNS

from waypoint.core.events import EventBus
from waypoint.rns.identity import IdentityManager

log = logging.getLogger(__name__)

# Content size cap for Phase 1 DIRECT messages (bytes, post-encode).
MAX_CONTENT_BYTES = 64 * 1024


class PeerUnknownError(Exception):
    """Raised when we have no identity/path for the destination yet."""


class MessageTooLargeError(Exception):
    pass


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class ChatRouter:
    def __init__(
        self,
        lxmf_dir: Path,
        identity_manager: IdentityManager,
        bus: EventBus,
        display_name: str = "",
    ) -> None:
        self._lxmf_dir = lxmf_dir
        self._identity_manager = identity_manager
        self._bus = bus
        self._display_name = display_name
        self._router: LXMF.LXMRouter | None = None
        self._delivery_destination: RNS.Destination | None = None
        self._pending: dict[str, LXMF.LXMessage] = {}  # outbound, hash_hex -> lxm

    def start(self) -> None:
        identity = self._identity_manager.identity
        self._lxmf_dir.mkdir(parents=True, exist_ok=True)
        router = LXMF.LXMRouter(
            identity=identity,
            storagepath=str(self._lxmf_dir),
            autopeer=True,
        )
        self._delivery_destination = router.register_delivery_identity(
            identity, display_name=self._display_name or None
        )
        router.register_delivery_callback(self._on_inbound)
        self._router = router
        log.info(
            "LXMF router started; address=%s", self.delivery_destination_hash_hex
        )

    # -- identity / addressing ------------------------------------------------

    @property
    def delivery_destination_hash_hex(self) -> str:
        assert self._delivery_destination is not None
        return self._delivery_destination.hash.hex()

    def set_display_name(self, name: str) -> None:
        self._display_name = name
        if self._delivery_destination is not None:
            self._delivery_destination.display_name = name or None

    # -- announcing -----------------------------------------------------------

    def announce(self) -> None:
        assert self._router is not None and self._delivery_destination is not None
        self._router.announce(self._delivery_destination.hash)
        log.info("Announced lxmf.delivery destination")

    # -- outbound -------------------------------------------------------------

    def send(self, peer_hash_hex: str, content: str, title: str = "") -> str:
        """Queue a direct LXMF message. Returns the message hash (hex)."""
        assert self._router is not None and self._delivery_destination is not None
        if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise MessageTooLargeError(
                f"message exceeds {MAX_CONTENT_BYTES} bytes; attachments come in Phase 2"
            )
        dest_hash = bytes.fromhex(peer_hash_hex)
        identity = RNS.Identity.recall(dest_hash)
        if identity is None:
            RNS.Transport.request_path(dest_hash)
            raise PeerUnknownError(peer_hash_hex)
        peer_dest = RNS.Destination(
            identity, RNS.Destination.OUT, RNS.Destination.SINGLE, "lxmf", "delivery"
        )
        lxm = LXMF.LXMessage(
            peer_dest,
            self._delivery_destination,
            content,
            title,
            desired_method=LXMF.LXMessage.DIRECT,
        )
        lxm.register_delivery_callback(self._on_outbound_delivered)
        lxm.register_failed_callback(self._on_outbound_failed)
        # pack() is guarded by `if not self.packed` and computes the message
        # hash deterministically; without this, lxm.hash is None until the
        # router's outbound thread packs it, and we couldn't track the message.
        lxm.pack()
        self._pending[lxm.hash.hex()] = lxm
        self._router.handle_outbound(lxm)
        return lxm.hash.hex()

    def poll_pending_states(self) -> list[tuple[str, int]]:
        """Return (hash_hex, state) for pending outbound messages whose state
        reached at least SENT. Belt-and-braces around the callbacks."""
        progressed = []
        for hash_hex, lxm in list(self._pending.items()):
            state = int(getattr(lxm, "state", 0) or 0)
            if state == LXMF.LXMessage.FAILED or state >= LXMF.LXMessage.SENT:
                progressed.append((hash_hex, state))
        return progressed

    def forget_pending(self, hash_hex: str) -> None:
        self._pending.pop(hash_hex, None)

    # -- callbacks (RNS worker threads!) --------------------------------------

    def _on_inbound(self, lxm: LXMF.LXMessage) -> None:
        try:
            self._bus.publish_from_thread(
                "message_received",
                {
                    "hash": lxm.hash.hex(),
                    "peer": lxm.source_hash.hex(),
                    "title": _as_text(lxm.title),
                    "content": _as_text(lxm.content),
                    "ts": getattr(lxm, "timestamp", None) or time.time(),
                    "signature_valid": bool(getattr(lxm, "signature_validated", False)),
                },
            )
        except Exception:  # noqa: BLE001
            log.exception("inbound delivery callback failed")

    def _on_outbound_delivered(self, lxm: LXMF.LXMessage) -> None:
        hash_hex = lxm.hash.hex()
        self._pending.pop(hash_hex, None)
        self._bus.publish_from_thread(
            "message_state", {"hash": hash_hex, "state": "delivered", "ts": time.time()}
        )

    def _on_outbound_failed(self, lxm: LXMF.LXMessage) -> None:
        hash_hex = lxm.hash.hex()
        self._pending.pop(hash_hex, None)
        self._bus.publish_from_thread(
            "message_state", {"hash": hash_hex, "state": "failed", "ts": time.time()}
        )
