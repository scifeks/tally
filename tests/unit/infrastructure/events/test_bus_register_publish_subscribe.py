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


async def test_register_publish_subscribe_ordered():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    _, q = await bus.subscribe("j1")

    events = [_ev("j1", i) for i in range(5)]
    for ev in events:
        await bus.publish(ev)
    await bus.close_job("j1")

    received = []
    while True:
        item = await asyncio.wait_for(q.get(), timeout=1.0)
        if item is EOS:
            break
        received.append(item)

    assert received == events


async def test_register_idempotent():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    await bus.register_job("j1", "scan")
    assert len(bus._jobs) == 1
