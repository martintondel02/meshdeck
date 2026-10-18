"""Thread-safe event bus bridging RNS worker threads into the asyncio loop.

The one rule of this codebase: RNS/LXMF callbacks fire on RNS worker threads.
They must never touch asyncio directly. Everything enters the loop through
EventBus.publish_from_thread(), which uses loop.call_soon_threadsafe().
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    type: str
    data: dict[str, Any]
    ts: float = field(default_factory=time.time)


Subscriber = Callable[[Event], Any]  # may return an awaitable


class EventBus:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[Event] | None = None
        self._subscribers: list[Subscriber] = []
        self._task: asyncio.Task[None] | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the application loop. Must be called from the loop thread."""
        self._loop = loop
        self._queue = asyncio.Queue()

    def subscribe(self, callback: Subscriber) -> None:
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def publish(self, type_: str, data: dict[str, Any]) -> None:
        """Publish from the loop thread."""
        assert self._queue is not None, "EventBus.bind() must be called first"
        self._queue.put_nowait(Event(type=type_, data=data))

    def publish_from_thread(self, type_: str, data: dict[str, Any]) -> None:
        """Publish from any thread (RNS callbacks use this)."""
        if self._loop is None:
            log.warning("EventBus not bound; dropping event %s", type_)
            return
        event = Event(type=type_, data=data)
        self._loop.call_soon_threadsafe(self._enqueue, event)

    def _enqueue(self, event: Event) -> None:
        # Runs on the loop thread via call_soon_threadsafe.
        if self._queue is not None:
            self._queue.put_nowait(event)

    async def start(self) -> None:
        assert self._queue is not None, "EventBus.bind() must be called first"
        self._task = asyncio.create_task(self._run(), name="eventbus")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        assert self._queue is not None
        while True:
            event = await self._queue.get()
            for callback in list(self._subscribers):
                try:
                    result = callback(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # noqa: BLE001 - subscribers must not kill the bus
                    log.exception("event subscriber failed for %s", event.type)
