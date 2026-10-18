"""Standalone headless MeshDeck chat node used by the integration harness.

Each instance runs in its own subprocess (RNS module state is process-global).
Exercises the real CoreService code path; talks JSON-lines on stdout for
debuggability, and uses sentinel files for ready/done synchronization.

Exit code 0 = done condition met; 1 = timeout/failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import RNS

from meshdeck.config import DEFAULT_SETTINGS, AppPaths
from meshdeck.core.service import CoreService

REANNOUNCE_SECONDS = 5
RETRY_SEND_SECONDS = 3
# When the target is offline (propagated delivery) the identity is seeded, so
# the only thing missing is the path; retry faster than the direct-send case.
RETRY_SEND_NO_PEER_SECONDS = 2
SYNC_RETRY_SECONDS = 5
SEND_CONCLUDE_TIMEOUT = 90


def jlog(**fields) -> None:
    print(json.dumps({"node": True, **fields}), flush=True)


def _split_set_pairs(raw: str) -> list[str]:
    """Split a comma-separated list of KEY=JSON pairs without breaking JSON.

    Values may be strings with commas or lists/objects (the structured
    ``interfaces`` setting), so only split on top-level commas outside quotes
    and outside brackets. This makes ``--set`` usable both repeatedly and as
    one comma-separated argument (e.g. from the shared launch_node helper,
    which passes one value per flag)."""
    pairs: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(raw):
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "\"'":
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == "," and depth == 0:
            pairs.append(raw[start:index])
            start = index + 1
    pairs.append(raw[start:])
    return [pair.strip() for pair in pairs if pair.strip()]


def parse_set_args(raw_values: list[str]) -> dict[str, Any]:
    """Parse ``--set KEY=JSON`` arguments into a settings dict.

    Only keys MeshDeck actually defines are accepted: a silent no-op for a
    typo would turn a boot test green while testing nothing."""
    seeded: dict[str, Any] = {}
    for raw in raw_values:
        for pair in _split_set_pairs(raw):
            key, separator, raw_value = pair.partition("=")
            key = key.strip()
            if not separator or not key:
                raise SystemExit(f"--set expects KEY=JSON, got {pair!r}")
            if key not in DEFAULT_SETTINGS:
                raise SystemExit(f"--set unknown settings key {key!r}")
            try:
                seeded[key] = json.loads(raw_value.strip())
            except json.JSONDecodeError as exc:
                raise SystemExit(
                    f"--set {key}: value must be JSON ({exc}): {raw_value.strip()!r}"
                ) from None
    return seeded


async def run(args: argparse.Namespace) -> int:
    paths = AppPaths(data_dir=Path(args.data_dir))
    paths.ensure()
    service = CoreService(paths)

    deadline = time.time() + args.timeout
    done_condition = asyncio.Event()
    result: dict = {"ok": False}

    peer_found = asyncio.Event()
    sent_hash: dict[str, str] = {}
    send_concluded = asyncio.Event()
    send_result: dict = {}
    return_code = [0]

    async def on_event(event) -> None:
        if event.type == "peer_announced":
            jlog(event="peer_announced", **event.data)
            if args.send_to and event.data["destination_hash"] == args.send_to:
                peer_found.set()
        elif event.type == "node_announced":
            jlog(event="node_announced", **event.data)
            if args.expect_node and event.data.get("hash") == args.expect_node:
                result["ok"] = True
                result["node_found"] = event.data
                done_condition.set()
        elif event.type == "message_received":
            jlog(event="message_received", **{k: v for k, v in event.data.items()})
            matched_text = args.expect and event.data.get("content") == args.expect
            matched_files = args.expect_attachments and event.data.get("attachments")
            if matched_text or matched_files:
                if not args.expect_from or event.data.get("peer") == args.expect_from:
                    if args.reply:
                        try:
                            service.send_message(event.data["peer"], args.reply)
                            jlog(event="replied", to=event.data["peer"])
                        except ValueError as exc:
                            jlog(event="reply_failed", reason=str(exc))
                            return_code[0] = 1
                    result["ok"] = True
                    result["got"] = event.data
                    done_condition.set()
        elif event.type in ("transfer_progress", "transfer_complete", "transfer_failed"):
            jlog(event=event.type, **event.data)
            result.setdefault("transfers", []).append(
                {"event": event.type, **event.data}
            )
        elif event.type == "message_state":
            jlog(event="message_state", **event.data)
            state = event.data.get("state")
            matches = bool(sent_hash) and event.data.get("hash") == sent_hash.get("hash")
            if matches and state in ("sent", "delivered", "failed"):
                send_result["state"] = state
                if state == "failed":
                    send_result["failed"] = True
                send_concluded.set()
            if (
                state == "delivered"
                and matches
                and not args.expect  # when expecting a reply, done waits for it
                and not args.exit_after_send
            ):
                result["ok"] = True
                result["delivered"] = sent_hash["hash"]
                done_condition.set()

    service.bus.subscribe(on_event)
    await service.start()

    # Optional loopback API: lets boot tests assert what the real /node and
    # /status endpoints report, not just what the harness chose to copy.
    api_server = None
    api_port: int | None = None
    api_token: str | None = None

    async def shutdown() -> None:
        if api_server is not None:
            await api_server.stop()
        await service.stop()

    if args.api_port is not None:
        from meshdeck.api.server import ApiServer
        from meshdeck.config import load_or_create_token

        api_token = load_or_create_token(paths.token_path)
        api_server = ApiServer(service, api_token)
        api_port = await api_server.start("127.0.0.1", args.api_port)
        jlog(event="api_ready", port=api_port)

    # Seed public identities for peers that are offline and have therefore never
    # announced to this node. Without this, an LXMF send to their address fails
    # with "no_path" before a propagation node ever gets involved.
    if args.seed_peer:
        for spec in args.seed_peer.split(","):
            peer_hash_hex, public_key_hex = spec.split(":", 1)
            public_key = bytes.fromhex(public_key_hex)
            if len(public_key) != RNS.Identity.KEYSIZE // 8:
                raise SystemExit(f"invalid public key length for {peer_hash_hex}")
            dest_hash = bytes.fromhex(peer_hash_hex)
            if dest_hash in RNS.Identity.known_destinations:
                # Already learned from an announce (which carries app_data such
                # as stamp costs); do not overwrite it with a bare key.
                continue
            RNS.Identity.remember(
                bytes(32), dest_hash, public_key
            )
            jlog(event="peer_seeded", hash=peer_hash_hex)

    if args.serve_node:
        # parent may have pre-written pages into <data>/pages
        await service.publish_node(node_name=args.serve_node, serve=True)
        jlog(event="node_published", hash=service.pages.node_destination_hash_hex)

    if args.fetch_page_from:
        async def fetcher() -> None:
            for attempt in range(60):
                try:
                    r = await service.browse_page(args.fetch_page_from, args.page_path)
                    result["fetched"] = r
                    if args.second_fetch_trigger:
                        # Hand the first (live) result to the parent, then wait
                        # until it has killed the host before refetching with a
                        # zero max_age so the cache can only be a stale fallback.
                        (Path(args.data_dir) / "first_fetch.json").write_text(
                            json.dumps(r), encoding="utf-8"
                        )
                        jlog(event="first_fetch_done", path=r["path"])
                        trigger = Path(args.second_fetch_trigger)
                        while not trigger.exists():
                            await asyncio.sleep(0.2)
                        r2 = await service.browse_page(
                            args.fetch_page_from, args.page_path, max_age=0
                        )
                        result["refetched"] = r2
                        jlog(event="second_fetch_done", stale=r2.get("stale"))
                    result["ok"] = True
                    done_condition.set()
                    return
                except ValueError as exc:
                    jlog(event="fetch_retry", attempt=attempt, error=str(exc))
                    await asyncio.sleep(3)

        asyncio.create_task(fetcher())

    if args.fetch_file_from and args.file_name:
        async def file_fetcher() -> None:
            import hashlib

            for attempt in range(40):
                try:
                    data, name, elapsed = await service.download_shared(
                        args.fetch_file_from,
                        args.file_name,
                        transfer_id=args.transfer_id,
                    )
                    result["ok"] = True
                    result["fetched_file"] = {
                        "name": name,
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "elapsed_ms": elapsed,
                    }
                    if args.transfer_id:
                        # let the EventBus deliver the final progress/complete
                        # events before the process exits and writes done.json
                        await asyncio.sleep(0.5)
                    done_condition.set()
                    return
                except ValueError as exc:
                    jlog(event="file_fetch_retry", attempt=attempt, error=str(exc))
                    await asyncio.sleep(3)

        asyncio.create_task(file_fetcher())

    if args.restart_watch_file:
        watch_path = Path(args.restart_watch_file)
        boot_mtime = watch_path.stat().st_mtime if watch_path.exists() else 0.0

        async def restart_watcher() -> None:
            """Mirrors the CLI's os.execv restart; triggered by file touch."""
            while True:
                if (
                    watch_path.exists()
                    and watch_path.stat().st_mtime > boot_mtime
                ):
                    jlog(event="restart_triggered")
                    await shutdown()
                    os.execv(sys.executable, [sys.executable, *sys.argv])
                await asyncio.sleep(0.4)

        asyncio.create_task(restart_watcher())

    status = service.status()
    info = service.identity_info()
    settings = service.get_settings()
    node_info = service.node_info()
    # The LXMF router's applied outbound propagation node is the runtime truth
    # behind the persisted `propagation_node_hash` setting (status only exposes
    # this node's own propagation destination, not the configured peer).
    router = getattr(service.chat, "_router", None)
    outbound_propagation_node = (
        router.get_outbound_propagation_node()
        if router is not None and hasattr(router, "get_outbound_propagation_node")
        else None
    )
    info.update(
        {
            "propagation_hosting": status["propagation_hosting"],
            "propagation_node_hash": status["propagation_node_hash"],
            "mode": status["mode"],
            "transport_enabled": status["transport_enabled"],
            # Runtime truth from RNS itself (status.transport_enabled only
            # echoes the settings value). A settings echo cannot catch the bug
            # class this matrix exists for.
            "rns_transport_enabled": RNS.Reticulum.transport_enabled(),
            "interfaces": status["interfaces"],
            "serve_pages": node_info["serve_pages"],
            "node_name": node_info["node_name"],
            "node_hash": node_info["node_hash"],
            "delivery_method": settings.get("delivery_method"),
            "propagation_node_setting": settings.get("propagation_node_hash"),
            "outbound_propagation_node": (
                outbound_propagation_node.hex() if outbound_propagation_node else ""
            ),
        }
    )
    if api_port is not None:
        info["api_port"] = api_port
        info["api_token"] = api_token
    # Public key lets a peer seed this node's identity while it is offline.
    info["public_key"] = service.identity.identity.get_public_key().hex()
    Path(args.ready_file).write_text(json.dumps(info), encoding="utf-8")
    jlog(event="ready", **info)

    if args.exit_after_ready:
        # Used by the harness to learn a node's addresses, then take it offline.
        await shutdown()
        return 0

    async def announce_loop() -> None:
        while not done_condition.is_set():
            try:
                await service.announce_now()
            except Exception as exc:  # noqa: BLE001
                jlog(event="announce_error", error=str(exc))
            await asyncio.sleep(REANNOUNCE_SECONDS)

    asyncio.create_task(announce_loop())

    if args.sync_retry and args.propagation_node:
        async def sync_loop() -> None:
            """C's first sync at startup can precede the path/identity to A."""
            while not done_condition.is_set():
                try:
                    ok = await asyncio.to_thread(
                        service.chat.sync_from_propagation_node
                    )
                    jlog(event="sync_retry", ok=ok)
                except Exception as exc:  # noqa: BLE001
                    jlog(event="sync_retry_failed", error=str(exc))
                await asyncio.sleep(SYNC_RETRY_SECONDS)

        asyncio.create_task(sync_loop())

    if args.send_to and (args.message or args.send_file):
        async def sender() -> None:
            if not args.send_without_peer_wait:
                try:
                    await asyncio.wait_for(peer_found.wait(), timeout=args.timeout)
                except asyncio.TimeoutError:
                    jlog(event="send_aborted", reason="peer never announced")
                    return
            retry_seconds = (
                RETRY_SEND_NO_PEER_SECONDS
                if args.send_without_peer_wait
                else RETRY_SEND_SECONDS
            )
            while not done_condition.is_set():
                try:
                    if args.send_file:
                        file_path = Path(args.send_file)
                        res = service.send_file(
                            args.send_to, file_path.name, file_path.read_bytes()
                        )
                    else:
                        res = service.send_message(args.send_to, args.message)
                    sent_hash["hash"] = res["hash"]
                    jlog(event="sent", **res)
                    break
                except ValueError as exc:
                    if str(exc) == "no_path":
                        jlog(event="send_retry", reason="no_path")
                        await asyncio.sleep(retry_seconds)
                    else:
                        jlog(event="send_failed", reason=str(exc))
                        result["ok"] = False
                        result["error"] = str(exc)
                        return_code[0] = 1
                        done_condition.set()
                        return
            else:
                return

            if args.exit_after_send:
                # Give the outbound thread time to hand the message to the
                # propagation node before this process exits.
                try:
                    await asyncio.wait_for(
                        send_concluded.wait(), timeout=SEND_CONCLUDE_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    jlog(event="send_concluded_timeout", hash=sent_hash["hash"])
                    result["ok"] = False
                    result["error"] = "send_timeout"
                    return_code[0] = 1
                else:
                    if send_result.get("failed"):
                        result["ok"] = False
                        result["error"] = "send_failed"
                        return_code[0] = 1
                    else:
                        result["ok"] = True
                        result["sent"] = sent_hash["hash"]
                        result["send_state"] = send_result.get("state")
                done_condition.set()

        asyncio.create_task(sender())

    while not done_condition.is_set():
        if time.time() > deadline:
            jlog(event="timeout", after=args.timeout)
            await shutdown()
            return 1
        await asyncio.sleep(0.2)

    Path(args.done_file).write_text(json.dumps(result), encoding="utf-8")
    jlog(event="done", **result)
    await shutdown()
    return return_code[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--display-name", default="")
    parser.add_argument("--extra-config-file", default=None,
                        help="file whose contents become the extra_config_text setting")
    parser.add_argument("--no-autointerface", action="store_true")
    parser.add_argument("--send-to", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--send-file", default=None, help="path to a file to send")
    parser.add_argument("--expect", default=None)
    parser.add_argument("--expect-attachments", action="store_true")
    parser.add_argument("--expect-from", default=None)
    parser.add_argument("--reply", default=None,
                        help="reply with this text when the expect condition matches")
    parser.add_argument("--restart-watch-file", default=None,
                        help="when this file is touched after boot, re-exec the process")
    parser.add_argument("--serve-node", default=None,
                        help="publish pages with this node name and announce")
    parser.add_argument("--fetch-page-from", default=None,
                        help="fetch a page from this node destination hash")
    parser.add_argument("--page-path", default="/page/index.mu")
    parser.add_argument("--second-fetch-trigger", default=None,
                        help="after the first page fetch, refetch when this file appears")
    parser.add_argument("--fetch-file-from", default=None,
                        help="download a shared file from this node destination hash")
    parser.add_argument("--file-name", default=None,
                        help="name of the shared file to download")
    parser.add_argument("--transfer-id", default=None,
                        help="request transfer progress events for this id")
    parser.add_argument("--expect-node", default=None,
                        help="done when a nomadnetwork.node announce with this hash arrives")
    parser.add_argument("--host-propagation", action="store_true",
                        help="seed host_propagation_node=True before start")
    parser.add_argument("--delivery-method", default=None,
                        help="seed delivery_method (direct/propagated/opportunistic)")
    parser.add_argument("--propagation-node", default=None,
                        help="seed propagation_node_hash (hex) of the store-and-forward node")
    parser.add_argument("--seed-peer", default=None,
                        metavar="HASH:PUBKEY_HEX[,HASH:PUBKEY_HEX]",
                        help="seed peer public identities so they need not be online")
    parser.add_argument("--send-without-peer-wait", action="store_true",
                        help="start sending immediately instead of waiting for the "
                             "target's announce (target is offline); retry no_path")
    parser.add_argument("--exit-after-send", action="store_true",
                        help="after the message reaches sent/delivered, stop and exit 0")
    parser.add_argument("--exit-after-ready", action="store_true",
                        help="write ready.json, stop the service and exit 0")
    parser.add_argument("--sync-retry", action="store_true",
                        help="retry sync_from_propagation_node every few seconds")
    parser.add_argument("--set", dest="set", action="append", default=[],
                        metavar="KEY=JSON",
                        help="seed a setting in the store before CoreService starts "
                             "(repeatable, or comma-separated KEY=JSON pairs); e.g. "
                             "--set serve_pages=true --set 'node_name=\"My Node\"'")
    parser.add_argument("--api-port", type=int, default=None,
                        help="also start the loopback REST API on this port "
                             "(0 = ephemeral); port and token go into ready.json")
    parser.add_argument("--ready-file", required=True)
    parser.add_argument("--done-file", required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    # Apply test overrides to default settings *before* the service starts by
    # pre-seeding the settings table: CoreService defaults come from settings,
    # so we write them into the db first via the same SettingsStore it uses.
    async def boot() -> int:
        paths = AppPaths(data_dir=Path(args.data_dir))
        paths.ensure()
        seeded = parse_set_args(args.set)
        if (
            args.extra_config_file
            or args.no_autointerface
            or args.display_name
            or args.host_propagation
            or args.delivery_method
            or args.propagation_node
            or seeded
        ):
            from meshdeck.config import SettingsStore
            from meshdeck.storage.db import Database

            db = Database(paths.db_path)
            db.open()
            store = SettingsStore(db)
            if args.no_autointerface:
                store.set("connect_autointerface", False)
            if args.extra_config_file:
                store.set("extra_config_text", Path(args.extra_config_file).read_text())
            if args.display_name:
                store.set("display_name", args.display_name)
            if args.host_propagation:
                store.set("host_propagation_node", True)
            if args.delivery_method:
                store.set("delivery_method", args.delivery_method)
            if args.propagation_node:
                store.set("propagation_node_hash", args.propagation_node)
            # Generic overrides win over the legacy convenience flags so a test
            # can express exactly the persisted state it wants.
            for key, value in seeded.items():
                store.set(key, value)
            db.close()
        return await run(args)

    try:
        return asyncio.run(boot())
    except KeyboardInterrupt:
        return 2


if __name__ == "__main__":
    sys.exit(main())
