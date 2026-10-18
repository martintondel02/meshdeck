"""CoreService: application facade owning component lifecycle and persistence.

The API layer only ever talks to this class; RNS/LXMF details stay inside.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import RNS

from meshdeck import __version__
from meshdeck.chat.peers import LxmfPeerAnnounceHandler
from meshdeck.chat.router import (
    ChatRouter,
    MessageTooLargeError,
    PeerUnknownError,
    PropagationNodeNotConfigured,
    sanitize_filename,
)
from meshdeck.config import (
    ATTACHMENT_STORAGE_MAX_MB_MAX,
    DEFAULT_SETTINGS,
    DELIVERY_METHODS,
    LOG_MAX_MB_MAX,
    PAGE_CACHE_MAX_BYTES_CEILING,
    PAGES_STORAGE_MAX_MB_MAX,
    PROPAGATION_STORAGE_LIMIT_MB_MAX,
    RETENTION_DAYS_MAX,
    SHARED_STORAGE_MAX_MB_MAX,
    VALID_MODES,
    AppPaths,
    SettingsStore,
    coerce_setting_int,
    mb_to_bytes,
)
from meshdeck.core.events import Event, EventBus
from meshdeck.pages.client import PageFetchError, fetch_file, fetch_page, normalize_page_path
from meshdeck.pages.files import SharedFileError, SharedStorageFull
from meshdeck.pages.hosting import NodeAnnounceHandler, PageHost
from meshdeck.pages.storage import PageNameError, PageStorageFull
from meshdeck.rns.config_gen import render_config, validate_interfaces
from meshdeck.rns.identity import IdentityManager
from meshdeck.rns.stack import InvalidConfigError, RnsStack, validate_interface_config
from meshdeck.storage import messages as msg_repo
from meshdeck.storage import nodes as node_repo
from meshdeck.storage import peers as peer_repo
from meshdeck.storage.attachments import attachment_usage, prune_attachments
from meshdeck.storage.db import Database
from meshdeck.storage.page_cache import DEFAULT_MAX_BYTES as DEFAULT_PAGE_CACHE_BYTES
from meshdeck.storage.page_cache import PageCache
from meshdeck.util.hexid import is_valid_hash_hex, is_valid_msg_hash_hex
from meshdeck.util.logs import log_usage

log = logging.getLogger(__name__)

# Settings that require an RNS restart to take effect. MeshDeck restarts the
# whole process (os.execv) because RNS.Reticulum is a never-cleared singleton
# in this rns version — an in-process re-instance raises OSError.
RESTART_SETTINGS = {
    "connect_autointerface",
    "public_entrypoints",
    "interfaces",
    "extra_config_text",
    "transport_enabled",
    "log_level",
}
EDITABLE_SETTINGS = set(DEFAULT_SETTINGS) | {"display_name", "mode"}

# Numeric storage/retention settings: (minimum, maximum). Validated before any
# key of a PUT is written; out-of-range or non-int values are rejected with 400.
NUMERIC_SETTINGS: dict[str, tuple[int, int]] = {
    "page_cache_max_bytes": (0, PAGE_CACHE_MAX_BYTES_CEILING),
    "propagation_storage_limit_mb": (0, PROPAGATION_STORAGE_LIMIT_MB_MAX),
    "attachment_storage_max_mb": (0, ATTACHMENT_STORAGE_MAX_MB_MAX),
    "attachment_retention_days": (0, RETENTION_DAYS_MAX),
    "shared_storage_max_mb": (0, SHARED_STORAGE_MAX_MB_MAX),
    "pages_storage_max_mb": (0, PAGES_STORAGE_MAX_MB_MAX),
    "message_retention_days": (0, RETENTION_DAYS_MAX),
    "log_max_mb": (0, LOG_MAX_MB_MAX),
}

# Message history retention is enforced at boot and then once a day.
MESSAGE_PRUNE_INTERVAL_SECONDS = 24 * 3600

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
        self.pages: PageHost | None = None
        self.page_cache: PageCache | None = None
        self.node_announce_handler: NodeAnnounceHandler | None = None
        self._announce_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._maintenance_task: asyncio.Task | None = None
        self._started_ts = 0.0
        self._db_lock = asyncio.Lock()
        # Set by the API; supervised by the CLI, which re-execs the process
        # (RNS can't be restarted in-process: Reticulum.__instance is never
        # cleared in this rns version).
        self.restart_requested: asyncio.Event | None = None

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        self.paths.ensure()
        self.db = Database(self.paths.db_path)
        self.db.open()
        self.settings = SettingsStore(self.db)
        self.page_cache = PageCache(self.db, max_bytes=self._page_cache_max_bytes())
        # Second belt: drop entries older than 30 days and cap the row count
        # once per boot. The byte ceiling above is enforced on every put.
        self.page_cache.prune()
        # Phase 7.1: apply the explicit attachment/retention policies at boot.
        self.prune_attachments()
        self.prune_message_history()

        self.bus.bind(asyncio.get_running_loop())
        await self.bus.start()
        self.bus.subscribe(self._persist_event)
        self.restart_requested = asyncio.Event()

        self.identity = IdentityManager(self.paths.identity_path)
        await asyncio.to_thread(self.identity.load_or_create)

        self.stack = RnsStack(self.paths.reticulum_dir, self.settings.all)
        log_file = str(self.paths.logs_dir / "reticulum.log")
        # NOTE: RNS.Reticulum installs SIGINT/SIGTERM handlers on construction,
        # which Python only allows on the main thread of the main interpreter.
        # The loop runs on the main thread, so start the stack directly here
        # (never via asyncio.to_thread). Interface bring-up can take a couple
        # of seconds with AutoInterface; acceptable during startup.
        self.stack.start(log_file)

        self.chat = ChatRouter(
            self.paths.lxmf_dir,
            self.paths.files_dir,
            self.identity,
            self.bus,
            display_name=self.settings.get("display_name") or "",
            delivery_method=self.settings.get("delivery_method") or "direct",
            propagation_node_hash=self.settings.get("propagation_node_hash") or "",
            host_propagation_node=bool(self.settings.get("host_propagation_node")),
            propagation_storage_limit_mb=self._propagation_storage_limit_mb(),
            attachment_storage_max_mb=self._attachment_storage_max_mb(),
            attachment_retention_days=self._attachment_retention_days(),
        )
        # NOTE: like RNS.Reticulum, LXMF.LXMRouter installs signal handlers in
        # its constructor — must run on the main thread. Construction is fast.
        self.chat.start()
        # Fetch any messages held for us by a configured propagation node.
        if self.settings.get("propagation_node_hash"):
            await asyncio.to_thread(self.chat.sync_from_propagation_node)

        self.announce_handler = LxmfPeerAnnounceHandler(
            self.bus, own_destination_hash_hex=self.chat.delivery_destination_hash_hex
        )
        RNS.Transport.register_announce_handler(self.announce_handler)

        # Page hosting: nomadnetwork.node destination + announce handler.
        self.pages = PageHost(
            self.paths.pages_dir,
            self.identity,
            self.bus,
            shared_dir=self.paths.shared_dir,
            pages_max_bytes=mb_to_bytes(self._pages_storage_max_mb()),
            shared_max_bytes=mb_to_bytes(self._shared_storage_max_mb()),
        )
        self.pages.start(node_name=self.settings.get("node_name") or "")
        self.node_announce_handler = NodeAnnounceHandler(
            self.bus, own_hash_hex=self.pages.node_destination_hash_hex
        )
        RNS.Transport.register_announce_handler(self.node_announce_handler)
        if self.settings.get("serve_pages"):
            await asyncio.to_thread(self.pages.announce)

        await asyncio.to_thread(self.chat.announce)
        self._announce_task = asyncio.create_task(self._announce_loop())
        self._poll_task = asyncio.create_task(self._poll_pending_loop())
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())
        self._started_ts = time.time()
        log.info("meshdeck core started")

    async def stop(self) -> None:
        for task in (self._announce_task, self._poll_task, self._maintenance_task):
            if task:
                task.cancel()
        if self.announce_handler is not None:
            RNS.Transport.deregister_announce_handler(self.announce_handler)
        await self.bus.stop()
        if self.stack is not None:
            self.stack.stop()
        if self.db is not None:
            self.db.close()
        log.info("meshdeck core stopped")

    async def _announce_loop(self) -> None:
        while True:
            interval_min = int(self.settings.get("announce_interval_minutes") or 0)
            if interval_min <= 0:
                await asyncio.sleep(60)
                continue
            await asyncio.sleep(interval_min * 60)
            try:
                await asyncio.to_thread(self.chat.announce)
                if self.pages is not None and self.settings.get("serve_pages"):
                    await asyncio.to_thread(self.pages.announce)
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

    async def _maintenance_loop(self) -> None:
        """Daily retention pass (message history); boot already ran once."""
        while True:
            await asyncio.sleep(MESSAGE_PRUNE_INTERVAL_SECONDS)
            try:
                removed = self.prune_message_history()
                if removed:
                    self.bus.publish("messages_pruned", {"removed": removed})
            except Exception:  # noqa: BLE001
                log.exception("daily message retention failed")

    # -- persistence subscriber (runs on the asyncio loop) ----------------------

    async def _persist_event(self, event: Event) -> None:
        assert self.db is not None
        async with self._db_lock:
            try:
                if event.type == "node_announced":
                    d = event.data
                    node_repo.upsert_node(self.db, d["hash"], d.get("name"))
                elif event.type == "peer_announced":
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
                            "fields_json": json.dumps(
                                {"attachments": d["attachments"]}
                            )
                            if d.get("attachments")
                            else None,
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

    # Disk-usage settings (Phase 6.3). Both are live-applied, never restart.

    def _page_cache_max_bytes(self) -> int:
        """Stored page-cache ceiling; falls back to the default if corrupt."""
        value = self.settings.get("page_cache_max_bytes", DEFAULT_PAGE_CACHE_BYTES)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return DEFAULT_PAGE_CACHE_BYTES

    def _propagation_storage_limit_mb(self) -> int:
        value = self.settings.get("propagation_storage_limit_mb", 256)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        return 256

    def _int_setting(self, key: str, default: int) -> int:
        """Read an integer setting defensively (corrupt JSON -> default)."""
        value = self.settings.get(key, default)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return default

    def _attachment_storage_max_mb(self) -> int:
        return self._int_setting("attachment_storage_max_mb", 512)

    def _attachment_retention_days(self) -> int:
        return self._int_setting("attachment_retention_days", 0)

    def _shared_storage_max_mb(self) -> int:
        return self._int_setting("shared_storage_max_mb", 1024)

    def _pages_storage_max_mb(self) -> int:
        return self._int_setting("pages_storage_max_mb", 256)

    def _message_retention_days(self) -> int:
        return self._int_setting("message_retention_days", 0)

    def _log_max_mb(self) -> int:
        return self._int_setting("log_max_mb", 10)

    # -- Phase 7.1 retention / pruning ----------------------------------------

    def prune_attachments(self) -> dict[str, Any]:
        """Apply the configured attachment policy (blobs only; rows survive)."""
        result = prune_attachments(
            self.paths.files_dir,
            max_bytes=mb_to_bytes(self._attachment_storage_max_mb()),
            retention_days=self._attachment_retention_days(),
        )
        if result.get("attachment_removed"):
            log.info(
                "attachment retention removed %s blob(s), freed %s bytes",
                result["attachment_removed"],
                result["attachment_freed_bytes"],
            )
        return result

    def prune_message_history(self) -> int:
        """Delete messages older than ``message_retention_days`` (0 = keep).

        Peers and discovered nodes are never touched. No automatic VACUUM: see
        ``storage.messages.prune_older_than`` for the documented reasoning.
        """
        days = self._message_retention_days()
        if days <= 0 or self.db is None:
            return 0
        cutoff = time.time() - days * 86400
        removed = msg_repo.prune_older_than(self.db, cutoff)
        if removed:
            log.info("message retention removed %s message(s) older than %s days", removed, days)
        return removed

    def storage_usage(self) -> dict[str, Any]:
        """Every bounded store's usage/limit, for /status and the Storage card."""
        attachment = attachment_usage(self.paths.files_dir)
        shared = (
            {
                "shared_bytes": self.pages.files.total_bytes(),
                "shared_files": self.pages.files.count(),
            }
            if self.pages is not None
            else {"shared_bytes": 0, "shared_files": 0}
        )
        pages = (
            {
                "pages_bytes": self.pages.store.total_bytes(),
                "pages_entries": self.pages.store.count(),
            }
            if self.pages is not None
            else {"pages_bytes": 0, "pages_entries": 0}
        )
        return {
            **self.page_cache_usage(),
            **attachment,
            "attachment_storage_max_bytes": mb_to_bytes(self._attachment_storage_max_mb()),
            "attachment_retention_days": self._attachment_retention_days(),
            **shared,
            "shared_storage_max_bytes": mb_to_bytes(self._shared_storage_max_mb()),
            **pages,
            "pages_storage_max_bytes": mb_to_bytes(self._pages_storage_max_mb()),
            "message_count": msg_repo.count_messages(self.db) if self.db is not None else 0,
            "message_retention_days": self._message_retention_days(),
            **log_usage(self.paths),
            "log_max_bytes": mb_to_bytes(self._log_max_mb()),
        }

    def page_cache_usage(self) -> dict[str, Any]:
        cache = self.page_cache
        if cache is None:
            return {"page_cache_bytes": 0, "page_cache_entries": 0, "page_cache_max_bytes": 0}
        return {
            "page_cache_bytes": cache.total_bytes(),
            "page_cache_entries": cache.count(),
            "page_cache_max_bytes": cache.max_bytes,
        }

    def clear_page_cache(self) -> dict[str, Any]:
        """Drop every cached page (safe: only the page_cache table is touched)."""
        if self.page_cache is None:
            raise ValueError("not_running")
        removed = self.page_cache.clear()
        self.bus.publish("page_cache_cleared", {"removed": removed})
        log.info("page cache cleared (%s entries)", removed)
        return {"cleared": removed, **self.page_cache_usage()}

    def status(self) -> dict[str, Any]:
        store_bytes = self.chat.propagation_store_bytes if self.chat else None
        return {
            "version": __version__,
            "mode": self.settings.get("mode"),
            "rns_running": bool(self.stack and self.stack.running),
            "transport_enabled": self.stack.transport_enabled() if self.stack else False,
            "interfaces": self.stack.interfaces() if self.stack else [],
            "peers": len(peer_repo.list_peers(self.db)),
            "uptime_seconds": round(time.time() - self._started_ts, 1),
            "propagation_hosting": bool(self.chat and self.chat.propagation_hosting),
            "propagation_node_hash": (
                self.chat.propagation_node_hash_hex if self.chat else ""
            ),
            # Phase 6.3: disk usage, so hosting doesn't silently fill a disk.
            # propagation_store_bytes is LXMF's message store (None = not
            # hosting / unreadable); the limit is in MB, 0 = unlimited.
            "propagation_store_bytes": store_bytes,
            "propagation_storage_limit_mb": self._propagation_storage_limit_mb(),
            "propagation_storage_limit_bytes": (
                self.chat.propagation_storage_limit_bytes if self.chat else 0
            ),
            **self.storage_usage(),
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
        rows = msg_repo.list_messages(self.db, peer_hash, before=before, limit=limit)
        for row in rows:
            available = self._attachment_availability(row)
            if available is not None:
                row["attachments_available"] = available
        return rows

    def _attachment_availability(self, row: dict[str, Any]) -> list[bool] | None:
        """Per-attachment blob presence for an inbound message (None if N/A).

        Pruned blobs keep their message metadata; the UI uses this to render a
        non-clickable "attachment no longer stored" tombstone."""
        if row.get("direction") != msg_repo.INBOUND or not row.get("fields_json"):
            return None
        try:
            meta = json.loads(row["fields_json"]).get("attachments") or []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return None
        if not meta:
            return None
        return [
            self._attachment_blob(
                row["peer_hash"], row["hash"], int(entry.get("index", -1))
            )
            is not None
            for entry in meta
            if isinstance(entry, dict)
        ]

    def _ensure_peer_row(self, peer_hash: str) -> None:
        """Guarantee the peers row exists before inserting a message.

        messages.peer_hash has a foreign key, and a send can win the race with
        the peer's announce (or target a manually added address), which made
        the API return 500 FOREIGN KEY constraint failed *after* LXMF had
        already sent the message."""
        if peer_repo.get_peer(self.db, peer_hash) is not None:
            return
        identity_hash = peer_hash
        try:
            identity = RNS.Identity.recall(bytes.fromhex(peer_hash))
            if identity is not None:
                identity_hash = identity.hash.hex()
        except Exception:  # noqa: BLE001 - never block sending on this lookup
            log.debug("identity recall failed for %s", peer_hash, exc_info=True)
        peer_repo.ensure_peer(self.db, peer_hash, identity_hash)

    def _record_outbound(
        self,
        msg_hash: str,
        peer_hash: str,
        title: str,
        content: str,
        attachments_meta: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._ensure_peer_row(peer_hash)
        msg_repo.insert_message(
            self.db,
            {
                "hash": msg_hash,
                "peer_hash": peer_hash,
                "direction": msg_repo.OUTBOUND,
                "state": msg_repo.SENDING,
                "title": title,
                "content": content,
                "fields_json": json.dumps({"attachments": attachments_meta})
                if attachments_meta
                else None,
            },
        )
        self.bus.publish(
            "message_state", {"hash": msg_hash, "peer": peer_hash, "state": msg_repo.SENDING}
        )
        return {"hash": msg_hash, "state": msg_repo.SENDING, "peer": peer_hash}

    def _peer_stamp_cost(self, peer_hash: str) -> int | None:
        peer = peer_repo.get_peer(self.db, peer_hash)
        if peer and isinstance(peer.get("stamp_cost"), int) and peer["stamp_cost"] > 0:
            return int(peer["stamp_cost"])
        return None

    def send_message(self, peer_hash: str, content: str, title: str = "") -> dict[str, Any]:
        """Raises ValueError with a machine-readable code on failure."""
        if not is_valid_hash_hex(peer_hash):
            raise ValueError("invalid_hash")
        try:
            msg_hash = self.chat.send(
                peer_hash, content, title, stamp_cost=self._peer_stamp_cost(peer_hash)
            )
        except PeerUnknownError:
            raise ValueError("no_path") from None
        except MessageTooLargeError:
            raise ValueError("too_large") from None
        except PropagationNodeNotConfigured:
            raise ValueError("no_propagation_node") from None
        return self._record_outbound(msg_hash, peer_hash, title, content)

    def send_file(
        self, peer_hash: str, filename: str, data: bytes, caption: str = ""
    ) -> dict[str, Any]:
        """Send one file as an LXMF attachment. Raises ValueError with a code."""
        if not is_valid_hash_hex(peer_hash):
            raise ValueError("invalid_hash")
        try:
            msg_hash = self.chat.send(
                peer_hash,
                caption,
                attachments=[(filename, data)],
                stamp_cost=self._peer_stamp_cost(peer_hash),
            )
        except PeerUnknownError:
            raise ValueError("no_path") from None
        except MessageTooLargeError as exc:
            raise ValueError("too_large") from exc
        except PropagationNodeNotConfigured:
            raise ValueError("no_propagation_node") from None
        attachments_meta = [
            {
                "name": sanitize_filename(filename),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        ]
        return self._record_outbound(msg_hash, peer_hash, "", caption, attachments_meta)

    def add_peer(self, peer_hash: str) -> dict[str, Any]:
        """Manually add a peer by hash; requests a network path if unknown."""
        if not is_valid_hash_hex(peer_hash):
            raise ValueError("invalid_hash")
        peer_hash = peer_hash.lower()
        existing = peer_repo.get_peer(self.db, peer_hash)
        dest_hash = bytes.fromhex(peer_hash)
        identity = RNS.Identity.recall(dest_hash)
        known = identity is not None
        if not known:
            RNS.Transport.request_path(dest_hash)
        if existing is None:
            peer_repo.ensure_peer(
                self.db, peer_hash, identity.hash.hex() if identity else peer_hash
            )
        self.bus.publish(
            "peer_added", {"hash": peer_hash, "known": known, "path_requested": not known}
        )
        return {
            "peer": peer_repo.get_peer(self.db, peer_hash),
            "known": known,
            "path_requested": not known,
        }

    def _attachment_blob(
        self, peer_hash: str, msg_hash: str, index: int
    ) -> Path | None:
        if not (is_valid_hash_hex(peer_hash) and is_valid_msg_hash_hex(msg_hash)):
            return None
        if index < 0 or index > 64:
            return None
        base = self.paths.files_dir.resolve()
        directory = (base / peer_hash / msg_hash).resolve()
        if not directory.is_relative_to(base) or not directory.is_dir():
            return None
        for candidate in sorted(directory.glob(f"{index}_*")):
            if candidate.is_file() and candidate.resolve().is_relative_to(base):
                return candidate
        return None

    def get_attachment(
        self, peer_hash: str, msg_hash: str, index: int
    ) -> tuple[Path, str] | None:
        """Resolve a stored inbound attachment for download. (path, safe_name)"""
        candidate = self._attachment_blob(peer_hash, msg_hash, index)
        if candidate is None:
            return None
        return candidate, candidate.name[len(str(index)) + 1 :]

    def attachment_known(self, peer_hash: str, msg_hash: str, index: int) -> bool:
        """True when the message metadata lists this attachment but the blob is gone.

        Lets the download route answer ``404 attachment_pruned`` instead of a
        generic ``not_found`` after retention removed the blob."""
        if not (is_valid_hash_hex(peer_hash) and is_valid_msg_hash_hex(msg_hash)):
            return False
        if index < 0 or index > 64:
            return False
        row = msg_repo.get_message(self.db, msg_hash)
        if row is None or row["peer_hash"] != peer_hash:
            return False
        if row.get("direction") != msg_repo.INBOUND or not row.get("fields_json"):
            return False
        try:
            meta = json.loads(row["fields_json"]).get("attachments") or []
        except (json.JSONDecodeError, TypeError, AttributeError):
            return False
        return any(
            isinstance(entry, dict) and int(entry.get("index", -1)) == index
            for entry in meta
        )

    def get_settings(self) -> dict[str, Any]:
        return self.settings.all()

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        restart_required = False
        # Validate numeric disk/retention limits before writing anything, so a
        # bad value in the same PUT cannot leave earlier keys half-applied.
        # Out-of-range is rejected (400), never silently clamped.
        limits: dict[str, int] = {}
        for key, (minimum, maximum) in NUMERIC_SETTINGS.items():
            if key in updates:
                limits[key] = coerce_setting_int(key, updates[key], minimum, maximum)
        # Side effects the caller/UI can report (pruned counts, evictions).
        effects: dict[str, Any] = {}
        for key, value in updates.items():
            if key not in EDITABLE_SETTINGS:
                continue
            if key in limits:
                value = limits[key]
            if key == "mode" and value not in VALID_MODES:
                raise ValueError("invalid_mode")
            if key == "delivery_method" and value not in DELIVERY_METHODS:
                raise ValueError("invalid_delivery_method")
            if key == "propagation_node_hash" and value and not is_valid_hash_hex(value):
                raise ValueError("invalid_propagation_node")
            if key == "interfaces":
                if not isinstance(value, list):
                    raise ValueError("invalid_interfaces")
                problems = validate_interfaces([e for e in value if isinstance(e, dict)])
                if problems or not all(isinstance(e, dict) for e in value):
                    details = "; ".join(problems or ["entries must be objects"])
                    raise ValueError("invalid_interfaces: " + details)
            if key in RESTART_SETTINGS and self.settings.get(key) != value:
                restart_required = True
            self.settings.set(key, value)
        if any(k in updates for k in ("delivery_method", "propagation_node_hash")):
            applied = self.chat.apply_delivery_settings(
                method=self.settings.get("delivery_method"),
                propagation_node_hash=self.settings.get("propagation_node_hash"),
            )
            self.bus.publish("settings_updated", applied)
        if "page_cache_max_bytes" in limits and self.page_cache is not None:
            evicted = self.page_cache.set_max_bytes(limits["page_cache_max_bytes"])
            self.bus.publish(
                "settings_updated",
                {
                    "page_cache_max_bytes": limits["page_cache_max_bytes"],
                    "page_cache_bytes": self.page_cache.total_bytes(),
                    "evicted": evicted,
                },
            )
        if "propagation_storage_limit_mb" in limits and self.chat is not None:
            # LXMF applies the cap in its own store-clean job (within ~2 min
            # while hosting); we only hand it the value.
            applied = self.chat.set_propagation_storage_limit_mb(
                limits["propagation_storage_limit_mb"]
            )
            self.bus.publish(
                "settings_updated",
                {
                    "propagation_storage_limit_mb": applied,
                    "propagation_storage_limit_bytes": (
                        self.chat.propagation_storage_limit_bytes
                    ),
                },
            )
        if "host_propagation_node" in updates and self.chat is not None:
            wanted = bool(self.settings.get("host_propagation_node"))
            if wanted != self.chat.propagation_hosting:
                # Live-apply: LXMRouter.enable/disable_propagation work on a
                # running router and announce the new state immediately.
                applied = self.chat.set_propagation_hosting(wanted)
                self.bus.publish(
                    "settings_updated",
                    {
                        "host_propagation_node": applied,
                        "propagation_node_hash": self.chat.propagation_node_hash_hex,
                    },
                )
        # Phase 7.1: live-apply the new bounds. Saving a retention value is the
        # explicit user action that authorises the first prune; nothing is
        # deleted silently in the background beyond the documented policy.
        if "attachment_storage_max_mb" in limits or "attachment_retention_days" in limits:
            applied_limits = {
                "attachment_storage_max_mb": self._attachment_storage_max_mb(),
                "attachment_retention_days": self._attachment_retention_days(),
            }
            if self.chat is not None:
                applied_limits = self.chat.set_attachment_limits(
                    applied_limits["attachment_storage_max_mb"],
                    applied_limits["attachment_retention_days"],
                )
            pruned = self.prune_attachments()
            effects.update(pruned)
            self.bus.publish(
                "settings_updated",
                {**applied_limits, **pruned},
            )
        if "shared_storage_max_mb" in limits and self.pages is not None:
            applied = self.pages.files.set_max_bytes(
                mb_to_bytes(limits["shared_storage_max_mb"])
            )
            self.bus.publish(
                "settings_updated",
                {
                    "shared_storage_max_bytes": applied,
                    "shared_bytes": self.pages.files.total_bytes(),
                },
            )
        if "pages_storage_max_mb" in limits and self.pages is not None:
            applied = self.pages.store.set_max_bytes(
                mb_to_bytes(limits["pages_storage_max_mb"])
            )
            self.bus.publish(
                "settings_updated",
                {"pages_storage_max_bytes": applied, "pages_bytes": self.pages.store.total_bytes()},
            )
        if "message_retention_days" in limits:
            removed = self.prune_message_history()
            effects["messages_pruned"] = removed
            self.bus.publish(
                "settings_updated",
                {
                    "message_retention_days": limits["message_retention_days"],
                    "messages_pruned": removed,
                },
            )
        if "log_max_mb" in limits:
            # Rotation itself happens at the next startup (before RNS starts).
            self.bus.publish("settings_updated", {"log_max_mb": limits["log_max_mb"]})
        result = self.settings.all()
        result["restart_required"] = restart_required
        result["effects"] = effects
        return result

    async def announce_now(self) -> dict[str, Any]:
        await asyncio.to_thread(self.chat.announce)
        if self.pages is not None and self.settings.get("serve_pages"):
            await asyncio.to_thread(self.pages.announce)
        return {"announced": True, "ts": time.time()}

    # -- restart (network reconfigure) ------------------------------------------

    def validate_network_config(self) -> list[str]:
        """Render the config for CURRENT settings and pre-flight it.

        Returns a list of human-readable problems (empty = bootable)."""
        import tempfile

        with tempfile.TemporaryDirectory(prefix="wp-cfgcheck-") as tmp:
            cfg = Path(tmp) / "config"
            cfg.write_text(render_config(self.settings.all(), log_file="x"), encoding="utf-8")
            try:
                validate_interface_config(cfg)
            except InvalidConfigError as exc:
                return [str(exc)]
        return []

    def request_restart(self) -> dict[str, Any]:
        """Ask the supervising CLI to re-exec the process with fresh settings."""
        problems = self.validate_network_config()
        if problems:
            raise ValueError("invalid_config:" + "|".join(problems))
        assert self.restart_requested is not None
        self.bus.publish("restart_scheduled", {})
        # Defer the flip slightly so the HTTP response can complete first.
        asyncio.get_running_loop().call_later(0.4, self.restart_requested.set)
        return {"restarting": True}

    # -- pages / node hosting ---------------------------------------------------

    def list_pages(self) -> list[dict[str, Any]]:
        return self.pages.store.list_pages()

    def read_page(self, name: str) -> str:
        try:
            return self.pages.store.read(name)
        except PageNameError:
            raise ValueError("invalid_page_name") from None
        except FileNotFoundError:
            raise ValueError("not_found") from None

    def save_page(self, name: str, content: str) -> dict[str, Any]:
        try:
            result = self.pages.store.write(name, content)
        except PageStorageFull:
            raise ValueError("pages_storage_full") from None
        except PageNameError as exc:
            raise ValueError("invalid_page_name") from exc
        self.pages.register_all_pages()
        return result

    def delete_page(self, name: str) -> None:
        try:
            self.pages.store.delete(name)
        except PageNameError:
            raise ValueError("invalid_page_name") from None

    async def publish_node(
        self, node_name: str | None = None, serve: bool | None = None
    ) -> dict[str, Any]:
        """Update node presentation and announce immediately when enabled."""
        if node_name is not None:
            self.settings.set("node_name", node_name.strip())
            self.pages.set_node_name(node_name.strip())
        if serve is not None:
            self.settings.set("serve_pages", bool(serve))
        announced = False
        if self.settings.get("serve_pages"):
            await asyncio.to_thread(self.pages.announce)
            announced = True
        return {
            "node_hash": self.pages.node_destination_hash_hex,
            "node_name": self.pages.node_name,
            "serve_pages": bool(self.settings.get("serve_pages")),
            "announced": announced,
        }

    def node_info(self) -> dict[str, Any]:
        return {
            "node_hash": self.pages.node_destination_hash_hex,
            "node_name": self.pages.node_name,
            "serve_pages": bool(self.settings.get("serve_pages")),
        }

    def list_nodes(self) -> list[dict[str, Any]]:
        return node_repo.list_nodes(self.db)

    # -- shared files (node hosting) --------------------------------------------

    def list_shared(self) -> list[dict[str, Any]]:
        return self.pages.files.list_files()

    def share_file(self, name: str, data: bytes) -> dict[str, Any]:
        try:
            result = self.pages.files.save(name, data)
        except SharedStorageFull:
            raise ValueError("shared_storage_full") from None
        except SharedFileError as exc:
            raise ValueError(f"invalid_file:{exc}") from None
        self.pages.register_all_files()
        return result

    def unshare_file(self, name: str) -> None:
        try:
            self.pages.files.delete(name)
        except SharedFileError:
            raise ValueError("invalid_file_name") from None

    def read_shared(self, name: str) -> tuple[bytes, str]:
        try:
            data = self.pages.files.read(name)
        except SharedFileError:
            raise ValueError("invalid_file_name") from None
        if data is None:
            raise ValueError("not_found")
        return data, name

    def _transfer_emitter(
        self, transfer_id: str | None, path: str, kind: str
    ) -> Callable[[float], None] | None:
        """Throttled progress callback for the WS transfer events.

        Runs on an RNS worker thread (link.request's progress callback), so it
        must only ever use EventBus.publish_from_thread. Throttled to 10 %
        deltas or 250 ms so a fast 8 MiB file cannot flood the socket.
        """
        if not transfer_id:
            return None
        state = {"progress": -1.0, "ts": 0.0}

        def emit(fraction: float) -> None:
            progress = max(0.0, min(1.0, float(fraction)))
            now = time.time()
            if (
                progress < 1.0
                and progress - state["progress"] < 0.10
                and now - state["ts"] < 0.25
            ):
                return
            state["progress"] = progress
            state["ts"] = now
            self.bus.publish_from_thread(
                "transfer_progress",
                {
                    "id": transfer_id,
                    "path": path,
                    "progress": round(progress, 3),
                    "kind": kind,
                },
            )

        return emit

    def _transfer_failed(
        self, transfer_id: str | None, path: str, error: str
    ) -> None:
        if transfer_id:
            self.bus.publish(
                "transfer_failed",
                {"id": transfer_id, "path": path, "error": error},
            )

    async def download_shared(
        self,
        node_hash: str,
        name: str,
        transfer_id: str | None = None,
    ) -> tuple[bytes, str, float]:
        """Fetch a file hosted on another node; returns (bytes, name, elapsed)."""
        path = f"/file/{name}"
        started = time.time()
        progress = self._transfer_emitter(transfer_id, path, "file")
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(fetch_file, node_hash, name, progress_cb=progress),
                timeout=120,
            )
        except PageFetchError as exc:
            self._transfer_failed(transfer_id, path, str(exc))
            raise ValueError(str(exc)) from None
        except TimeoutError:
            self._transfer_failed(transfer_id, path, "link_timeout")
            raise ValueError("link_timeout") from None
        elapsed = round((time.time() - started) * 1000, 1)
        if transfer_id:
            self.bus.publish(
                "transfer_complete",
                {
                    "id": transfer_id,
                    "path": path,
                    "name": name,
                    "bytes": len(data),
                    "elapsed_ms": elapsed,
                    "sha256": hashlib.sha256(data).hexdigest(),
                },
            )
        return data, name, elapsed

    async def _cache_get(self, node_hash: str, path: str) -> dict[str, Any] | None:
        if self.page_cache is None:
            return None
        async with self._db_lock:
            return self.page_cache.get(node_hash, path)

    async def _cache_put(self, node_hash: str, path: str, content: str) -> None:
        if self.page_cache is None:
            return
        async with self._db_lock:
            self.page_cache.put(node_hash, path, content)

    @staticmethod
    def _cached_page(
        node_hash: str,
        path: str,
        cached: dict[str, Any],
        *,
        stale: bool,
        elapsed_ms: float,
        error: str | None = None,
    ) -> dict[str, Any]:
        content = str(cached["content"])
        result = {
            "node_hash": node_hash,
            "path": path,
            "content": content,
            "bytes": int(cached["content_bytes"] or len(content.encode("utf-8"))),
            "elapsed_ms": elapsed_ms,
            "served_from_cache": True,
            "stale": stale,
            "cached_ts": cached["fetched_ts"],
        }
        if error is not None:
            result["error"] = error
        return result

    async def browse_page(
        self,
        node_hash: str,
        path: str,
        transfer_id: str | None = None,
        *,
        refresh: bool = False,
        max_age: float = 3600.0,
    ) -> dict[str, Any]:
        path = normalize_page_path(path)
        started = time.time()
        cached = await self._cache_get(node_hash, path)
        if (
            cached is not None
            and not refresh
            and (time.time() - float(cached["fetched_ts"])) <= max_age
        ):
            return self._cached_page(
                node_hash, path, cached, stale=False, elapsed_ms=0.0
            )

        progress = self._transfer_emitter(transfer_id, path, "page")
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(fetch_page, node_hash, path, progress_cb=progress),
                timeout=40,
            )
        except PageFetchError as exc:
            error = str(exc)
            self._transfer_failed(transfer_id, path, error)
            if cached is not None:
                return self._cached_page(
                    node_hash,
                    path,
                    cached,
                    stale=True,
                    elapsed_ms=round((time.time() - started) * 1000, 1),
                    error=error,
                )
            raise ValueError(error) from None
        except TimeoutError:
            self._transfer_failed(transfer_id, path, "link_timeout")
            if cached is not None:
                return self._cached_page(
                    node_hash,
                    path,
                    cached,
                    stale=True,
                    elapsed_ms=round((time.time() - started) * 1000, 1),
                    error="link_timeout",
                )
            raise ValueError("link_timeout") from None

        elapsed = round((time.time() - started) * 1000, 1)
        content = data.decode("utf-8", "replace")
        await self._cache_put(node_hash, path, content)
        if transfer_id:
            self.bus.publish(
                "transfer_complete",
                {
                    "id": transfer_id,
                    "path": path,
                    "bytes": len(data),
                    "elapsed_ms": elapsed,
                },
            )
        return {
            "node_hash": node_hash,
            "path": path,
            "content": content,
            "bytes": len(data),
            "elapsed_ms": elapsed,
            "served_from_cache": False,
            "stale": False,
            "cached_ts": None,
        }
