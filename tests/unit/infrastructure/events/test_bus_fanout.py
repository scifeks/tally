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


async def test_all_subscribers_receive_all_events():
    bus = EventBus()
    await bus.register_job("j1", "scan", subscriber_size=128)

    subs = []
    for _ in range(3):
        sub_id, q = await bus.subscribe("j1")
        subs.append((sub_id, q))

    events = [_ev("j1", i) for i in range(50)]
    for ev in events:
        await bus.publish(ev)
    await bus.close_job("j1")

    for sub_id, q in subs:
        received = []
        while True:
            item = await asyncio.wait_for(q.get(), timeout=2.0)
            if item is EOS:
                break
            received.append(item)
        assert received == events, (
            f"Subscriber {sub_id} did not receive all 50 events in order"
        )
