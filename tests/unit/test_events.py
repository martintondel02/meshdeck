"""EventBus thread-to-loop bridging and ordering."""

import asyncio
import threading

from meshdeck.core.events import EventBus


async def test_events_delivered_in_order():
    bus = EventBus()
    bus.bind(asyncio.get_running_loop())
    received = []
    bus.subscribe(lambda ev: received.append(ev.type))
    await bus.start()

    for i in range(5):
        bus.publish(f"loop_{i}", {})

    def from_other_thread():
        bus.publish_from_thread("thread_1", {})
        bus.publish_from_thread("thread_2", {})

    t = threading.Thread(target=from_other_thread)
    t.start()
    t.join()

    await asyncio.sleep(0.2)
    await bus.stop()
    assert received == ["loop_0", "loop_1", "loop_2", "loop_3", "loop_4", "thread_1", "thread_2"]


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    bus.bind(asyncio.get_running_loop())
    received = []
    cb = lambda ev: received.append(ev.type)  # noqa: E731
    bus.subscribe(cb)
    await bus.start()
    bus.publish("a", {})
    await asyncio.sleep(0.05)  # let the bus deliver "a" first
    bus.unsubscribe(cb)
    bus.publish("b", {})
    await asyncio.sleep(0.05)
    await bus.stop()
    assert received == ["a"]
