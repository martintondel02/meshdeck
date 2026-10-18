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

from meshdeck.config import AppPaths
from meshdeck.core.service import CoreService

REANNOUNCE_SECONDS = 5
RETRY_SEND_SECONDS = 3


def jlog(**fields) -> None:
    print(json.dumps({"node": True, **fields}), flush=True)


async def run(args: argparse.Namespace) -> int:
    paths = AppPaths(data_dir=Path(args.data_dir))
    paths.ensure()
    service = CoreService(paths)

    deadline = time.time() + args.timeout
    done_condition = asyncio.Event()
    result: dict = {"ok": False}

    peer_found = asyncio.Event()
    sent_hash: dict[str, str] = {}
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
        elif event.type == "message_state":
            jlog(event="message_state", **event.data)
            if (
                event.data.get("state") == "delivered"
                and sent_hash
                and event.data.get("hash") == sent_hash["hash"]
                and not args.expect  # when expecting a reply, done waits for it
            ):
                result["ok"] = True
                result["delivered"] = sent_hash["hash"]
                done_condition.set()

    service.bus.subscribe(on_event)
    await service.start()

    if args.serve_node:
        # parent may have pre-written pages into <data>/pages
        await service.publish_node(node_name=args.serve_node, serve=True)
        jlog(event="node_published", hash=service.pages.node_destination_hash_hex)

    if args.fetch_page_from:
        async def fetcher() -> None:
            for attempt in range(60):
                try:
                    r = await service.browse_page(args.fetch_page_from, args.page_path)
                    result["ok"] = True
                    result["fetched"] = r
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
                        args.fetch_file_from, args.file_name
                    )
                    result["ok"] = True
                    result["fetched_file"] = {
                        "name": name,
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "elapsed_ms": elapsed,
                    }
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
                    await service.stop()
                    os.execv(sys.executable, [sys.executable, *sys.argv])
                await asyncio.sleep(0.4)

        asyncio.create_task(restart_watcher())

    info = service.identity_info()
    Path(args.ready_file).write_text(json.dumps(info), encoding="utf-8")
    jlog(event="ready", **info)

    async def announce_loop() -> None:
        while not done_condition.is_set():
            try:
                await service.announce_now()
            except Exception as exc:  # noqa: BLE001
                jlog(event="announce_error", error=str(exc))
            await asyncio.sleep(REANNOUNCE_SECONDS)

    asyncio.create_task(announce_loop())

    if args.send_to and (args.message or args.send_file):
        async def sender() -> None:
            try:
                await asyncio.wait_for(peer_found.wait(), timeout=args.timeout)
            except asyncio.TimeoutError:
                jlog(event="send_aborted", reason="peer never announced")
                return
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
                    return
                except ValueError as exc:
                    if str(exc) == "no_path":
                        jlog(event="send_retry", reason="no_path")
                        await asyncio.sleep(RETRY_SEND_SECONDS)
                    else:
                        raise

        asyncio.create_task(sender())

    while not done_condition.is_set():
        if time.time() > deadline:
            jlog(event="timeout", after=args.timeout)
            await service.stop()
            return 1
        await asyncio.sleep(0.2)

    Path(args.done_file).write_text(json.dumps(result), encoding="utf-8")
    jlog(event="done", **result)
    await service.stop()
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
    parser.add_argument("--fetch-file-from", default=None,
                        help="download a shared file from this node destination hash")
    parser.add_argument("--file-name", default=None,
                        help="name of the shared file to download")
    parser.add_argument("--expect-node", default=None,
                        help="done when a nomadnetwork.node announce with this hash arrives")
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
        if args.extra_config_file or args.no_autointerface or args.display_name:
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
            db.close()
        return await run(args)

    try:
        return asyncio.run(boot())
    except KeyboardInterrupt:
        return 2


if __name__ == "__main__":
    sys.exit(main())
