"""LXMF chat router wrapper: inbound delivery handling and outbound sending."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

import LXMF
import RNS

from meshdeck.core.events import EventBus
from meshdeck.rns.identity import IdentityManager

log = logging.getLogger(__name__)

# Content size cap for plain DIRECT messages (bytes, post-encode).
MAX_CONTENT_BYTES = 64 * 1024
# Total attachment bytes per message in the current phase. MeshDeck nodes
# accept inbound transfers up to ROUTER_DELIVERY_LIMIT kilobytes; other LXMF
# clients typically cap at 1 MB, so oversize sends to them may fail cleanly
# (message state -> failed, shown in the UI with an explanation).
MAX_ATTACHMENT_TOTAL_BYTES = 1536 * 1024  # 1.5 MiB
ROUTER_DELIVERY_LIMIT_KB = 2048  # inbound direct-transfer cap: 2,048,000 bytes

_METHODS = {
    "direct": LXMF.LXMessage.DIRECT,
    "propagated": LXMF.LXMessage.PROPAGATED,
    "opportunistic": LXMF.LXMessage.OPPORTUNISTIC,
}

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str) -> str:
    """Reduce an attacker-controlled attachment name to a safe basename.

    Clients may percent-encode separator characters, so decode first, THEN
    strip directories, THEN neutralize anything unusual."""
    decoded = urllib.parse.unquote(name)
    base = decoded.replace("\\", "/").split("/")[-1].strip().strip(".")
    base = _UNSAFE_FILENAME.sub("_", base)
    return (base[:120] or "attachment")


class PeerUnknownError(Exception):
    """Raised when we have no identity/path for the destination yet."""


class MessageTooLargeError(Exception):
    pass


class PropagationNodeNotConfigured(Exception):
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
        files_dir: Path,
        identity_manager: IdentityManager,
        bus: EventBus,
        display_name: str = "",
        delivery_method: str = "direct",
        propagation_node_hash: str = "",
        host_propagation_node: bool = False,
    ) -> None:
        self._lxmf_dir = lxmf_dir
        self._files_dir = files_dir
        self._identity_manager = identity_manager
        self._bus = bus
        self._display_name = display_name
        self._delivery_method = delivery_method if delivery_method in _METHODS else "direct"
        self._propagation_node_hash = propagation_node_hash
        self._host_propagation_node = bool(host_propagation_node)
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
            delivery_limit=ROUTER_DELIVERY_LIMIT_KB,
        )
        self._delivery_destination = router.register_delivery_identity(
            identity, display_name=self._display_name or None
        )
        router.register_delivery_callback(self._on_inbound)
        self._router = router
        self.apply_delivery_settings()
        # Apply the persisted hosting preference after the router exists. The
        # flag is already True here, so reset it first: the setter's equality
        # guard would otherwise skip enable_propagation() (no message store,
        # no handlers, no propagation announce, while status still said true).
        host_propagation = self._host_propagation_node
        self._host_propagation_node = False
        if host_propagation:
            self.set_propagation_hosting(True)
        log.info("LXMF router started; address=%s", self.delivery_destination_hash_hex)

    # -- identity / addressing ------------------------------------------------

    @property
    def delivery_destination_hash_hex(self) -> str:
        assert self._delivery_destination is not None
        return self._delivery_destination.hash.hex()

    def set_display_name(self, name: str) -> None:
        self._display_name = name
        if self._delivery_destination is not None:
            self._delivery_destination.display_name = name or None

    # -- delivery configuration -----------------------------------------------

    def apply_delivery_settings(
        self, method: str | None = None, propagation_node_hash: str | None = None
    ) -> dict[str, Any]:
        """Apply delivery method / propagation node settings (live, no restart)."""
        assert self._router is not None
        if method is not None and method in _METHODS:
            self._delivery_method = method
        if propagation_node_hash is not None:
            self._propagation_node_hash = propagation_node_hash.strip().lower()

        outbound_node = None
        if self._propagation_node_hash:
            try:
                self._router.set_outbound_propagation_node(
                    bytes.fromhex(self._propagation_node_hash)
                )
                outbound_node = self._propagation_node_hash
            except Exception:  # noqa: BLE001
                log.exception("failed to set outbound propagation node")
                outbound_node = None
        return {
            "delivery_method": self._delivery_method,
            "propagation_node": outbound_node,
        }

    @property
    def propagation_hosting(self) -> bool:
        return self._host_propagation_node

    @property
    def propagation_node_hash_hex(self) -> str:
        """This node's own store-and-forward address (stable, hosting or not)."""
        assert self._router is not None
        return self._router.propagation_destination.hash.hex()

    def set_propagation_hosting(self, enabled: bool) -> bool:
        """Start/stop being a store-and-forward node for others (live)."""
        assert self._router is not None
        enabled = bool(enabled)
        if enabled == self._host_propagation_node:
            return enabled
        if enabled:
            self._router.enable_propagation()
        else:
            self._router.disable_propagation()
        self._host_propagation_node = enabled
        log.info("Propagation node hosting %s", "enabled" if enabled else "disabled")
        return enabled

    def sync_from_propagation_node(self) -> bool:
        """Ask the configured propagation node for our stored messages."""
        if not self._propagation_node_hash or self._router is None:
            return False
        try:
            # LXMF calls Link.identify() with this argument so the propagation
            # node knows whose mailbox to serve: it must be OUR identity (with
            # the private key), not the propagation node's public identity.
            # Passing the latter fails with "identity does not hold a private
            # key" and no messages are ever fetched.
            self._router.request_messages_from_propagation_node(
                self._identity_manager.identity
            )
            log.info("requested message sync from propagation node")
            return True
        except Exception:  # noqa: BLE001
            log.exception("propagation node sync failed")
            return False

    # -- announcing -----------------------------------------------------------

    def announce(self) -> None:
        assert self._router is not None and self._delivery_destination is not None
        self._router.announce(self._delivery_destination.hash)
        log.info("Announced lxmf.delivery destination")

    # -- outbound -------------------------------------------------------------

    def send(
        self,
        peer_hash_hex: str,
        content: str,
        title: str = "",
        attachments: list[tuple[str, bytes]] | None = None,
        method: str | None = None,
        stamp_cost: int | None = None,
    ) -> str:
        """Queue an LXMF message. Returns the message hash (hex).

        When ``stamp_cost`` is set (announced by the recipient), LXMF defers
        the outbound, generates the proof-of-work stamp in a worker pool, and
        then sends — the message hash stays stable through the re-pack because
        stamps are not part of the hashed payload."""
        assert self._router is not None and self._delivery_destination is not None
        if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise MessageTooLargeError(f"message exceeds {MAX_CONTENT_BYTES} bytes")

        fields: dict[int, Any] | None = None
        attachments_meta: list[dict[str, Any]] = []
        if attachments:
            total = sum(len(data) for _, data in attachments)
            if total > MAX_ATTACHMENT_TOTAL_BYTES:
                raise MessageTooLargeError(
                    f"attachments total {total} bytes, limit is"
                    f" {MAX_ATTACHMENT_TOTAL_BYTES}"
                )
            fields = {
                LXMF.FIELD_FILE_ATTACHMENTS: [
                    [sanitize_filename(name).encode("utf-8"), data]
                    for name, data in attachments
                ]
            }
            attachments_meta = [
                {
                    "name": sanitize_filename(name),
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
                for name, data in attachments
            ]

        desired = _METHODS.get(method or self._delivery_method, LXMF.LXMessage.DIRECT)
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
            fields=fields,
            desired_method=desired,
            stamp_cost=stamp_cost,
            # attach a reply ticket so the receiver can answer without
            # generating their own stamp for this conversation
            include_ticket=True,
        )
        lxm.register_delivery_callback(self._on_outbound_delivered)
        lxm.register_failed_callback(self._on_outbound_failed)
        # pack() is guarded by `if not self.packed` and computes the message
        # hash deterministically; without this, lxm.hash is None until the
        # router's outbound thread packs it, and we couldn't track the message.
        try:
            lxm.pack()
        except Exception:  # noqa: BLE001 - e.g. stamp policy issues
            log.exception("failed to pack outgoing message")
            raise MessageTooLargeError("could not pack message") from None
        lxm.meshdeck_attachments = attachments_meta  # type: ignore[attr-defined]
        self._pending[lxm.hash.hex()] = lxm
        try:
            self._router.handle_outbound(lxm)
        except OSError as exc:
            self._pending.pop(lxm.hash.hex(), None)
            if "propagation node" in str(exc).lower():
                raise PropagationNodeNotConfigured from None
            raise
        return lxm.hash.hex()

    @staticmethod
    def attachments_of(msg_hash_hex: str, lxm_or_meta: Any) -> list[dict[str, Any]]:
        return getattr(lxm_or_meta, "meshdeck_attachments", None) or []

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

    # -- inbound --------------------------------------------------------------

    def _on_inbound(self, lxm: LXMF.LXMessage) -> None:
        try:
            attachments = self._save_attachments(lxm)
            self._bus.publish_from_thread(
                "message_received",
                {
                    "hash": lxm.hash.hex(),
                    "peer": lxm.source_hash.hex(),
                    "title": _as_text(lxm.title),
                    "content": _as_text(lxm.content),
                    "ts": getattr(lxm, "timestamp", None) or time.time(),
                    "signature_valid": bool(getattr(lxm, "signature_validated", False)),
                    "attachments": attachments,
                },
            )
        except Exception:  # noqa: BLE001
            log.exception("inbound delivery callback failed")

    def _save_attachments(self, lxm: LXMF.LXMessage) -> list[dict[str, Any]]:
        """Persist inbound attachments to <files>/<peer>/<msg>/ and return meta."""
        attachments = (lxm.fields or {}).get(LXMF.FIELD_FILE_ATTACHMENTS) or []
        meta: list[dict[str, Any]] = []
        for index, entry in enumerate(attachments):
            try:
                if not (isinstance(entry, (list, tuple)) and len(entry) >= 2):
                    continue
                name = sanitize_filename(_as_text(entry[0]))
                data = entry[1]
                if not isinstance(data, (bytes, bytearray)):
                    continue
                target_dir = (
                    self._files_dir / lxm.source_hash.hex() / lxm.hash.hex()
                ).resolve()
                if not str(target_dir).startswith(str(self._files_dir.resolve())):
                    continue
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{index}_{name}"
                target.write_bytes(bytes(data))
                meta.append(
                    {
                        "index": index,
                        "name": name,
                        "size": len(data),
                        "sha256": hashlib.sha256(bytes(data)).hexdigest(),
                    }
                )
            except Exception:  # noqa: BLE001
                log.exception("failed to save attachment %s", index)
        return meta

    # -- callbacks (RNS worker threads!) --------------------------------------

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
