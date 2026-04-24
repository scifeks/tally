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


async def test_unsubscribe_before_dispatch_no_error():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    sub_id1, _ = await bus.subscribe("j1")
    _, q2 = await bus.subscribe("j1")

    await bus.unsubscribe("j1", sub_id1)

    events = [_ev("j1", i) for i in range(5)]
    for ev in events:
        await bus.publish(ev)
    await bus.close_job("j1")

    received = []
    while True:
        item = await asyncio.wait_for(q2.get(), timeout=1.0)
        if item is EOS:
            break
        received.append(item)

    assert received == events
    state = bus._jobs.get("j1")
    assert state is None or sub_id1 not in state.subscribers


async def test_unsubscribe_after_dispatch_no_error():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    sub_id1, q1 = await bus.subscribe("j1")
    _, q2 = await bus.subscribe("j1")

    events = [_ev("j1", i) for i in range(5)]
    for ev in events:
        await bus.publish(ev)

    # drain q1 partially, then unsubscribe
    await asyncio.wait_for(q1.get(), timeout=1.0)
    await bus.unsubscribe("j1", sub_id1)

    await bus.close_job("j1")

    received = []
    while True:
        item = await asyncio.wait_for(q2.get(), timeout=1.0)
        if item is EOS:
            break
        received.append(item)

    assert received == events
