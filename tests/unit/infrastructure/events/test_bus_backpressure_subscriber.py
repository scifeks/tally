import asyncio
from datetime import UTC, datetime

from infrastructure.events import EventBus
from infrastructure.events.types import EOS, BusEvent


def _ev(job_id: str, n: int) -> BusEvent:
    return BusEvent(
        event_id=f"evt{n}",
        job_id=job_id,
        stream="scan",
        event_type="log",
        payload={"n": n},
        ts=datetime.now(tz=UTC),
    )


async def test_drop_oldest_subscriber_receives_most_recent():
    bus = EventBus()
    await bus.register_job("j1", "scan", subscriber_size=4)
    _, q = await bus.subscribe("j1")
    # Capture before close_job; the dispatcher pops the job from
    # bus._jobs when it processes EOS. Awaiting the dispatcher below
    # lets it fully drain into the subscriber queue before we consume,
    # which is what exercises drop-oldest: with the per-event yield
    # in _dispatch (added to avoid SSE batching), a same-coroutine
    # consumer would otherwise interleave and the queue would never
    # fill up.
    dispatcher = bus._jobs["j1"].dispatcher
    assert dispatcher is not None

    events = [_ev("j1", i) for i in range(10)]
    for ev in events:
        await bus.publish(ev)
    await bus.close_job("j1")
    await dispatcher

    received = []
    while True:
        item = await asyncio.wait_for(q.get(), timeout=2.0)
        if item is EOS:
            break
        received.append(item)

    assert len(received) < 10
    assert received[-1].payload["n"] == 9


async def test_slow_subscriber_does_not_block_fast_subscriber():
    bus = EventBus()
    await bus.register_job("j1", "scan", subscriber_size=64)

    await bus.subscribe("j1")  # slow subscriber, queue never drained
    _, fast_q = await bus.subscribe("j1")

    events = [_ev("j1", i) for i in range(10)]
    for ev in events:
        await bus.publish(ev)
    await bus.close_job("j1")

    fast_received = []
    while True:
        item = await asyncio.wait_for(fast_q.get(), timeout=2.0)
        if item is EOS:
            break
        fast_received.append(item)

    assert fast_received == events
