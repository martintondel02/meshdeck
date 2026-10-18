"""CLI entry point: python -m waypoint / `waypoint`."""

from __future__ import annotations

import argparse
import asyncio
import logging
import webbrowser
from pathlib import Path

from waypoint import __version__
from waypoint.api.server import ApiServer
from waypoint.config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    AppPaths,
    default_data_dir,
    load_or_create_token,
)
from waypoint.core.service import CoreService

log = logging.getLogger("waypoint")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="waypoint",
        description="Waypoint — an all-in-one Reticulum application (chat, files, pages, hosting).",
    )
    parser.add_argument("--version", action="version", version=f"waypoint {__version__}")
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
    # Repo layout: <repo>/waypoint/__main__.py -> <repo>/frontend/dist
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
    await service.start()

    server = ApiServer(service, token, static_dir=resolve_static_dir())
    port = await server.start(args.host, args.port)
    url = f"http://{args.host}:{port}/?token={token}"

    print(f"Waypoint {__version__} (data: {paths.data_dir})")
    print(f"Web UI:  {url}")
    print(f"API:     http://{args.host}:{port}/api/v1/status (Bearer token)")
    if args.open_browser:
        webbrowser.open(url)

    try:
        await asyncio.Event().wait()  # run until cancelled
    finally:
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
