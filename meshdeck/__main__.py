"""CLI entry point: python -m meshdeck / `meshdeck`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import webbrowser
from pathlib import Path

from meshdeck import __version__
from meshdeck.api.server import ApiServer
from meshdeck.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    AppPaths,
    default_data_dir,
    load_or_create_token,
)
from meshdeck.core.service import CoreService
from meshdeck.rns.stack import InvalidConfigError

log = logging.getLogger("meshdeck")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meshdeck",
        description="MeshDeck — an all-in-one Reticulum application (chat, files, pages, hosting).",
    )
    parser.add_argument("--version", action="version", version=f"meshdeck {__version__}")
    parser.add_argument("--data-dir", type=Path, default=None,
                        help="override the data directory (default: platform user data dir)")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"bind host (default {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"bind port (default {DEFAULT_PORT}, auto-increments if busy)")
    parser.add_argument("--open-browser", action="store_true",
                        help="open the web UI in your default browser")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parser


def resolve_static_dir() -> Path | None:
    # PyInstaller bundle: datas are unpacked under sys._MEIPASS (or _internal
    # in 6.x onedir mode); the frozen app also looks for a sibling dist dir.
    for candidate in (
        getattr(sys, "_MEIPASS", None) and Path(sys._MEIPASS) / "frontend" / "dist",
        getattr(sys, "_MEIPASS", None) and Path(sys._MEIPASS).parent / "frontend" / "dist",
    ):
        if candidate and candidate.exists():
            return candidate
    # Repo layout: <repo>/meshdeck/__main__.py -> <repo>/frontend/dist
    repo_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if repo_dist.exists():
        return repo_dist
    return None


async def amain(args: argparse.Namespace) -> int:
    data_dir = args.data_dir or default_data_dir()
    paths = AppPaths(data_dir=data_dir)
    paths.ensure()
    token = load_or_create_token(paths.token_path)

    service = CoreService(paths)
    try:
        await service.start()
    except InvalidConfigError as exc:
        print(f"Reticulum configuration error: {exc}")
        print(f"(edit via settings, or fix/remove {paths.reticulum_config_path})")
        return 2

    server = ApiServer(service, token, static_dir=resolve_static_dir())
    port = await server.start(args.host, args.port)
    url = f"http://{args.host}:{port}/?token={token}"

    print(f"MeshDeck {__version__} (data: {paths.data_dir})")
    print(f"Web UI:  {url}")
    print(f"API:     http://{args.host}:{port}/api/v1/status (Bearer token)")
    if args.open_browser:
        webbrowser.open(url)

    async def restart_watch() -> None:
        """Network config changes are applied by re-executing the process;
        this rns version cannot re-create its Reticulum singleton in-process."""
        assert service.restart_requested is not None
        await service.restart_requested.wait()
        log.info("restart requested — stopping and re-executing process")
        await server.stop()
        await service.stop()
        argv = [sys.executable, "-m", "meshdeck", "--data-dir", str(paths.data_dir),
                "--host", args.host, "--port", str(port)]
        if args.verbose:
            argv.append("-v")
        os.execv(sys.executable, argv)

    watcher = asyncio.create_task(restart_watch())
    try:
        await asyncio.Event().wait()  # run until cancelled
    finally:
        watcher.cancel()
        await server.stop()
        await service.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        print("\nbye.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
