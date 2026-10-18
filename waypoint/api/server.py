"""Loopback-only HTTP + WebSocket API and static frontend hosting."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any

from aiohttp import WSMsgType, web

from waypoint.api.schemas import (
    BadRequest,
    optional_str,
    optional_str_from_path,
    require_hash,
    require_str,
)
from waypoint.chat.router import MAX_ATTACHMENT_TOTAL_BYTES
from waypoint.core.events import Event
from waypoint.core.service import CoreService

log = logging.getLogger(__name__)

MAX_PORT_ATTEMPTS = 20

_NOT_BUILT_PAGE = """<!doctype html><meta charset="utf-8"><title>Waypoint</title>
<body style="font-family:system-ui;margin:3em">
<h1>Waypoint backend is running</h1>
<p>The web UI hasn't been built yet. In the repo, run
<code>cd frontend &amp;&amp; pnpm install &amp;&amp; pnpm run build</code>,
then restart.</p>
<p>API: <code>/api/v1/status</code> (Bearer token required),
WebSocket: <code>/ws?token=…</code></p>
"""


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status)


def _error(status: int, code: str, message: str) -> web.Response:
    return _json({"ok": False, "error": {"code": code, "message": message}}, status=status)


class ApiServer:
    def __init__(
        self,
        service: CoreService,
        token: str,
        static_dir: Path | None = None,
    ) -> None:
        self.service = service
        self._token = token
        self.static_dir = static_dir
        self._runner: web.AppRunner | None = None
        self.bound_port: int | None = None

    # -- auth ------------------------------------------------------------

    def _token_ok(self, request: web.Request) -> bool:
        supplied = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            supplied = auth[7:].strip()
        elif "token" in request.query:
            supplied = request.query["token"]
        return supplied is not None and hmac.compare_digest(supplied, self._token)

    @web.middleware
    async def _auth_middleware(self, request: web.Request, handler):
        if request.path.startswith("/api/") or request.path == "/ws":
            if not self._token_ok(request):
                return _error(401, "unauthorized", "missing or invalid token")
        try:
            return await handler(request)
        except BadRequest as exc:
            return _error(400, exc.code, exc.message)
        except ValueError as exc:
            return _error(400, str(exc), "request failed validation")

    # -- app construction --------------------------------------------------

    def build_app(self) -> web.Application:
        app = web.Application(middlewares=[self._auth_middleware])
        app.router.add_get("/api/v1/status", self._status)
        app.router.add_get("/api/v1/identity", self._identity)
        app.router.add_post("/api/v1/identity/display_name", self._set_display_name)
        app.router.add_get("/api/v1/peers", self._peers)
        app.router.add_post("/api/v1/peers", self._add_peer)
        app.router.add_patch("/api/v1/peers/{hash}", self._patch_peer)
        app.router.add_get("/api/v1/messages", self._messages)
        app.router.add_post("/api/v1/messages", self._send_message)
        app.router.add_post("/api/v1/files", self._send_file)
        app.router.add_get(
            "/api/v1/attachments/{peer}/{msg}/{index}", self._download_attachment
        )
        app.router.add_get("/api/v1/settings", self._get_settings)
        app.router.add_put("/api/v1/settings", self._put_settings)
        app.router.add_post("/api/v1/announce", self._announce)
        app.router.add_get("/ws", self._websocket)
        app.router.add_get("/", self._index)
        app.router.add_get("/{tail:.*}", self._static_or_index)
        return app

    async def start(self, host: str, port: int) -> int:
        """Bind host:port, auto-incrementing on conflicts. Returns bound port."""
        app = self.build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        last_error: Exception | None = None
        for offset in range(MAX_PORT_ATTEMPTS):
            candidate = port + offset
            try:
                site = web.TCPSite(self._runner, host, candidate)
                await site.start()
                resolved = candidate
                if candidate == 0:  # ephemeral: read the actual port from the socket
                    server_obj = getattr(site, "_server", None)
                    if server_obj and server_obj.sockets:
                        resolved = int(server_obj.sockets[0].getsockname()[1])
                self.bound_port = resolved
                return resolved
            except OSError as exc:
                last_error = exc
                continue
        raise RuntimeError(f"no free port near {port}: {last_error}")

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # -- REST handlers ------------------------------------------------------

    async def _status(self, request: web.Request) -> web.Response:
        return _json(self.service.status())

    async def _identity(self, request: web.Request) -> web.Response:
        return _json(self.service.identity_info())

    async def _set_display_name(self, request: web.Request) -> web.Response:
        data = await request.json()
        name = require_str(data, "display_name", max_len=128)
        return _json(await self.service.set_display_name(name))

    async def _peers(self, request: web.Request) -> web.Response:
        return _json(self.service.list_peers())

    async def _add_peer(self, request: web.Request) -> web.Response:
        data = await request.json()
        peer_hash = require_hash(data, "hash")
        return _json(self.service.add_peer(peer_hash), status=201)

    async def _patch_peer(self, request: web.Request) -> web.Response:
        peer_hash = request.match_info["hash"]
        data = await request.json()
        nickname = optional_str(data, "nickname", max_len=128) if "nickname" in data else None
        blocked_raw = data.get("blocked")
        blocked = bool(blocked_raw) if blocked_raw is not None else None
        peer = self.service.update_peer(peer_hash, nickname=nickname, blocked=blocked)
        if peer is None:
            return _error(404, "not_found", "unknown peer")
        return _json(peer)

    async def _messages(self, request: web.Request) -> web.Response:
        peer_hash = optional_str_from_path(request.query.get("peer"))
        if peer_hash is None:
            return _error(400, "invalid_peer", "query param 'peer' must be a 32-char hex hash")
        before = request.query.get("before")
        before_ts = float(before) if before else None
        limit = min(int(request.query.get("limit", "50")), 200)
        return _json(self.service.list_messages(peer_hash, before=before_ts, limit=limit))

    async def _send_message(self, request: web.Request) -> web.Response:
        data = await request.json()
        peer_hash = require_hash(data, "peer")
        content = require_str(data, "content")
        title = optional_str(data, "title", max_len=512) or ""
        result = self.service.send_message(peer_hash, content, title)
        return _json(result, status=202)

    async def _get_settings(self, request: web.Request) -> web.Response:
        return _json(self.service.get_settings())

    async def _put_settings(self, request: web.Request) -> web.Response:
        data = await request.json()
        if not isinstance(data, dict):
            raise BadRequest("invalid_body", "expected a JSON object of setting updates")
        return _json(self.service.update_settings(data))

    async def _announce(self, request: web.Request) -> web.Response:
        return _json(await self.service.announce_now())

    async def _send_file(self, request: web.Request) -> web.Response:
        """Multipart upload: fields 'peer' (hash), 'file' (the payload),
        optional 'caption'. Enforces the attachment size cap while reading."""
        if not request.content_type.startswith("multipart/"):
            raise BadRequest("invalid_body", "expected multipart/form-data")
        peer_hash: str | None = None
        filename = "attachment"
        caption = ""
        data = bytearray()

        reader = await request.multipart()
        async for part in reader:  # type: ignore[union-attr]
            if part.name == "peer":
                peer_hash = (await part.text()).strip().lower()
            elif part.name == "caption":
                caption = (await part.text())[:512]
            elif part.name == "file":
                if part.filename:
                    filename = part.filename
                while True:
                    chunk = await part.read_chunk(64 * 1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_ATTACHMENT_TOTAL_BYTES:
                        raise BadRequest(
                            "too_large",
                            f"file exceeds {MAX_ATTACHMENT_TOTAL_BYTES} bytes",
                        )
        if peer_hash is None:
            raise BadRequest("missing_peer", "multipart field 'peer' is required")
        result = self.service.send_file(peer_hash, filename, bytes(data), caption)
        return _json(result, status=202)

    async def _download_attachment(self, request: web.Request) -> web.Response:
        resolved = self.service.get_attachment(
            request.match_info["peer"],
            request.match_info["msg"],
            int(request.match_info["index"]),
        )
        if resolved is None:
            return _error(404, "not_found", "attachment not found")
        path, safe_name = resolved
        return web.FileResponse(
            path, headers={"Content-Disposition": f'attachment; filename="{safe_name}"'}
        )

    # -- WebSocket -----------------------------------------------------------

    async def _websocket(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        queue: asyncio.Queue[Event] = asyncio.Queue()

        def on_event(event: Event) -> None:
            queue.put_nowait(event)

        self.service.bus.subscribe(on_event)

        async def forward() -> None:
            while True:
                event = await queue.get()
                await ws.send_str(
                    json.dumps({"type": "event", "event": event.type, "data": event.data})
                )

        forwarder = asyncio.create_task(forward())
        try:
            await ws.send_str(json.dumps({"type": "hello", "ts": time.time()}))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle_ws_command(ws, msg.data)
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            forwarder.cancel()
            self.service.bus.unsubscribe(on_event)
        return ws

    async def _handle_ws_command(self, ws: web.WebSocketResponse, raw: str) -> None:
        try:
            frame = json.loads(raw)
            if not isinstance(frame, dict) or frame.get("type") != "cmd":
                raise BadRequest("bad_frame", "expected {type:'cmd', cmd, data}")
            cmd_id = frame.get("id")
            cmd = frame.get("cmd")

            async def ack(payload: dict[str, Any]) -> None:
                await ws.send_str(
                    json.dumps({"type": "ack", "id": cmd_id, "ok": True, "data": payload})
                )

            if cmd == "ping":
                await ack({"pong": True})
            elif cmd == "send_message":
                data = frame.get("data") or {}
                peer_hash = require_hash(data, "peer")
                content = require_str(data, "content")
                title = optional_str(data, "title", max_len=512) or ""
                await ack(self.service.send_message(peer_hash, content, title))
            elif cmd == "announce":
                await ack(await self.service.announce_now())
            else:
                raise BadRequest("unknown_cmd", f"unknown command '{cmd}'")
        except BadRequest as exc:
            await ws.send_str(
                json.dumps(
                    {
                        "type": "error",
                        "id": frame.get("id") if isinstance(frame, dict) else None,
                        "ok": False,
                        "error": {"code": exc.code, "message": exc.message},
                    }
                )
            )
        except ValueError as exc:
            await ws.send_str(
                json.dumps(
                    {
                        "type": "error",
                        "id": frame.get("id") if isinstance(frame, dict) else None,
                        "ok": False,
                        "error": {"code": str(exc), "message": "request failed validation"},
                    }
                )
            )
        except Exception:  # noqa: BLE001
            log.exception("ws command failed")
            await ws.send_str(
                json.dumps(
                    {"type": "error", "id": None, "ok": False,
                     "error": {"code": "internal", "message": "internal error"}}
                )
            )

    # -- static frontend -------------------------------------------------------

    async def _index(self, request: web.Request) -> web.Response:
        index = (self.static_dir / "index.html") if self.static_dir else None
        if index and index.exists():
            return web.FileResponse(index)
        return web.Response(text=_NOT_BUILT_PAGE, content_type="text/html")

    async def _static_or_index(self, request: web.Request) -> web.Response:
        if self.static_dir and self.static_dir.exists():
            tail = request.match_info.get("tail", "")
            base = self.static_dir.resolve()
            candidate = (base / tail).resolve()
            if candidate.is_file() and candidate.is_relative_to(base):
                return web.FileResponse(candidate)
        return await self._index(request)
