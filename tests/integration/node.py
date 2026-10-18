"""Standalone headless Waypoint chat node used by the integration harness.

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
import sys
import time
from pathlib import Path

from waypoint.config import AppPaths
from waypoint.core.service import CoreService

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

    async def on_event(event) -> None:
        if event.type == "peer_announced":
            jlog(event="peer_announced", **event.data)
            if args.send_to and event.data["destination_hash"] == args.send_to:
                peer_found.set()
        elif event.type == "message_received":
            jlog(event="message_received", **{k: v for k, v in event.data.items()})
            if args.expect and event.data.get("content") == args.expect:
                if not args.expect_from or event.data.get("peer") == args.expect_from:
                    result["ok"] = True
                    result["got"] = event.data
                    done_condition.set()
        elif event.type == "message_state":
            jlog(event="message_state", **event.data)
            if (
                event.data.get("state") == "delivered"
                and sent_hash
                and event.data.get("hash") == sent_hash["hash"]
            ):
                result["ok"] = True
                result["delivered"] = sent_hash["hash"]
                done_condition.set()

    service.bus.subscribe(on_event)
    await service.start()

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

    if args.send_to and args.message:
        async def sender() -> None:
            try:
                await asyncio.wait_for(peer_found.wait(), timeout=args.timeout)
            except asyncio.TimeoutError:
                jlog(event="send_aborted", reason="peer never announced")
                return
            while not done_condition.is_set():
                try:
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
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--display-name", default="")
    parser.add_argument("--extra-config-file", default=None,
                        help="file whose contents become the extra_config_text setting")
    parser.add_argument("--no-autointerface", action="store_true")
    parser.add_argument("--send-to", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--expect", default=None)
    parser.add_argument("--expect-from", default=None)
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
            from waypoint.config import SettingsStore
            from waypoint.storage.db import Database

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
