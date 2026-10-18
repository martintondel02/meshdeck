"""CoreService: application facade owning component lifecycle and persistence.

The API layer only ever talks to this class; RNS/LXMF details stay inside.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import RNS

from waypoint import __version__
from waypoint.chat.peers import LxmfPeerAnnounceHandler
from waypoint.chat.router import ChatRouter, MessageTooLargeError, PeerUnknownError
from waypoint.config import DEFAULT_SETTINGS, VALID_MODES, AppPaths, SettingsStore
from waypoint.core.events import Event, EventBus
from waypoint.rns.identity import IdentityManager
from waypoint.rns.stack import RnsStack
from waypoint.storage import messages as msg_repo
from waypoint.storage import peers as peer_repo
from waypoint.storage.db import Database
from waypoint.util.hexid import is_valid_hash_hex

log = logging.getLogger(__name__)

# Settings that require an RNS restart to take effect (live reconfigure = Phase 4).
RESTART_SETTINGS = {
    "connect_autointerface",
    "public_entrypoints",
    "extra_config_text",
    "transport_enabled",
    "log_level",
}
EDITABLE_SETTINGS = set(DEFAULT_SETTINGS) | {"display_name", "mode"}

# poll interval for outbound message state progression (callback fallback)
PENDING_POLL_SECONDS = 2.0


class CoreService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths
        self.bus = EventBus()
        self.db: Database | None = None
        self.settings: SettingsStore | None = None
        self.identity: IdentityManager | None = None
        self.stack: RnsStack | None = None
        self.chat: ChatRouter | None = None
        self.announce_handler: LxmfPeerAnnounceHandler | None = None
        self._announce_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._started_ts = 0.0
        self._db_lock = asyncio.Lock()

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        self.paths.ensure()
        self.db = Database(self.paths.db_path)
        self.db.open()
        self.settings = SettingsStore(self.db)

        self.bus.bind(asyncio.get_running_loop())
        await self.bus.start()
        self.bus.subscribe(self._persist_event)

        self.identity = IdentityManager(self.paths.identity_path)
        await asyncio.to_thread(self.identity.load_or_create)

        self.stack = RnsStack(self.paths.reticulum_dir, self.settings.all)
        log_file = str(self.paths.logs_dir / "reticulum.log")
        await asyncio.to_thread(self.stack.start, log_file)

        self.chat = ChatRouter(
            self.paths.lxmf_dir,
            self.identity,
            self.bus,
            display_name=self.settings.get("display_name") or "",
        )
        await asyncio.to_thread(self.chat.start)

        self.announce_handler = LxmfPeerAnnounceHandler(
            self.bus, own_destination_hash_hex=self.chat.delivery_destination_hash_hex
        )
        RNS.Transport.register_announce_handler(self.announce_handler)

        await asyncio.to_thread(self.chat.announce)
        self._announce_task = asyncio.create_task(self._announce_loop())
        self._poll_task = asyncio.create_task(self._poll_pending_loop())
        self._started_ts = time.time()
        log.info("waypoint core started")

    async def stop(self) -> None:
        for task in (self._announce_task, self._poll_task):
            if task:
                task.cancel()
        if self.announce_handler is not None:
            RNS.Transport.deregister_announce_handler(self.announce_handler)
        await self.bus.stop()
        if self.stack is not None:
            self.stack.stop()
        if self.db is not None:
            self.db.close()
        log.info("waypoint core stopped")

    async def _announce_loop(self) -> None:
        while True:
            interval_min = int(self.settings.get("announce_interval_minutes") or 0)
            if interval_min <= 0:
                await asyncio.sleep(60)
                continue
            await asyncio.sleep(interval_min * 60)
            try:
                await asyncio.to_thread(self.chat.announce)
            except Exception:  # noqa: BLE001
                log.exception("periodic announce failed")

    async def _poll_pending_loop(self) -> None:
        while True:
            await asyncio.sleep(PENDING_POLL_SECONDS)
            try:
                for hash_hex, state in self.chat.poll_pending_states():
                    row = msg_repo.get_message(self.db, hash_hex)
                    if row and row["state"] in (msg_repo.SENDING, msg_repo.SENT):
                        self.chat.forget_pending(hash_hex)
                        if row["state"] != msg_repo.SENT:
                            msg_repo.update_message_state(self.db, hash_hex, msg_repo.SENT)
                            self.bus.publish(
                                "message_state", {"hash": hash_hex, "state": msg_repo.SENT}
                            )
            except Exception:  # noqa: BLE001
                log.exception("pending poll failed")

    # -- persistence subscriber (runs on the asyncio loop) ----------------------

    async def _persist_event(self, event: Event) -> None:
        assert self.db is not None
        async with self._db_lock:
            try:
                if event.type == "peer_announced":
                    d = event.data
                    peer_repo.upsert_peer(
                        self.db,
                        d["destination_hash"],
                        d["identity_hash"],
                        display_name=d.get("display_name"),
                        stamp_cost=d.get("stamp_cost"),
                    )
                elif event.type == "message_received":
                    d = event.data
                    identity = await asyncio.to_thread(
                        RNS.Identity.recall, bytes.fromhex(d["peer"])
                    )
                    identity_hash = identity.hash.hex() if identity else d["peer"]
                    peer_repo.ensure_peer(self.db, d["peer"], identity_hash)
                    msg_repo.insert_message(
                        self.db,
                        {
                            "hash": d["hash"],
                            "peer_hash": d["peer"],
                            "direction": msg_repo.INBOUND,
                            "state": msg_repo.RECEIVED,
                            "title": d.get("title"),
                            "content": d.get("content"),
                            "created_ts": d.get("ts"),
                        },
                    )
                elif event.type == "message_state":
                    d = event.data
                    msg_repo.update_message_state(
                        self.db,
                        d["hash"],
                        d["state"],
                        delivered_ts=d.get("ts") if d["state"] == msg_repo.DELIVERED else None,
                    )
            except Exception:  # noqa: BLE001
                log.exception("persistence failed for %s", event.type)

    # -- API-facing methods -----------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "version": __version__,
            "mode": self.settings.get("mode"),
            "rns_running": bool(self.stack and self.stack.running),
            "transport_enabled": self.stack.transport_enabled() if self.stack else False,
            "interfaces": self.stack.interfaces() if self.stack else [],
            "peers": len(peer_repo.list_peers(self.db)),
            "uptime_seconds": round(time.time() - self._started_ts, 1),
        }

    def identity_info(self) -> dict[str, Any]:
        return {
            "hash": self.chat.delivery_destination_hash_hex,
            "display_name": self.settings.get("display_name") or "",
            "identity_hash": self.identity.hash_hex,
        }

    async def set_display_name(self, name: str) -> dict[str, Any]:
        name = name.strip()
        self.settings.set("display_name", name)
        self.chat.set_display_name(name)
        await asyncio.to_thread(self.chat.announce)
        return self.identity_info()

    def list_peers(self) -> list[dict[str, Any]]:
        return peer_repo.list_peers(self.db)

    def update_peer(
        self, peer_hash: str, nickname: str | None = None, blocked: bool | None = None
    ) -> dict[str, Any] | None:
        peer_repo.update_peer(self.db, peer_hash, nickname=nickname, blocked=blocked)
        peer = peer_repo.get_peer(self.db, peer_hash)
        if peer:
            self.bus.publish("peer_updated", {"hash": peer_hash})
        return peer

    def list_messages(
        self, peer_hash: str, before: float | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        return msg_repo.list_messages(self.db, peer_hash, before=before, limit=limit)

    def send_message(self, peer_hash: str, content: str, title: str = "") -> dict[str, Any]:
        """Raises KeyError-ish ValueError subclasses; callers map to codes."""
        if not is_valid_hash_hex(peer_hash):
            raise ValueError("invalid_hash")
        try:
            msg_hash = self.chat.send(peer_hash, content, title)
        except PeerUnknownError:
            raise ValueError("no_path") from None
        except MessageTooLargeError:
            raise ValueError("too_large") from None
        msg_repo.insert_message(
            self.db,
            {
                "hash": msg_hash,
                "peer_hash": peer_hash,
                "direction": msg_repo.OUTBOUND,
                "state": msg_repo.SENDING,
                "title": title,
                "content": content,
            },
        )
        self.bus.publish(
            "message_state", {"hash": msg_hash, "peer": peer_hash, "state": msg_repo.SENDING}
        )
        return {"hash": msg_hash, "state": msg_repo.SENDING, "peer": peer_hash}

    def get_settings(self) -> dict[str, Any]:
        return self.settings.all()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        restart_required = False
        for key, value in updates.items():
            if key not in EDITABLE_SETTINGS:
                continue
            if key == "mode" and value not in VALID_MODES:
                raise ValueError("invalid_mode")
            if key in RESTART_SETTINGS and self.settings.get(key) != value:
                restart_required = True
            self.settings.set(key, value)
        result = self.settings.all()
        result["restart_required"] = restart_required
        return result

    async def announce_now(self) -> dict[str, Any]:
        await asyncio.to_thread(self.chat.announce)
        return {"announced": True, "ts": time.time()}
