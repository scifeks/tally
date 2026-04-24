import asyncio
from datetime import UTC, datetime

import pytest

from infrastructure.events import EventBus
from infrastructure.events.types import BusEvent


def _ev(job_id: str, n: int) -> BusEvent:
    return BusEvent(
        event_id=f"evt{n}",
        job_id=job_id,
        stream="scan",
        event_type="log",
        payload={"n": n},
        ts=datetime.now(tz=UTC),
    )


async def test_producer_blocks_when_input_queue_full():
    bus = EventBus()
    await bus.register_job("j1", "scan", input_size=2)
    state = bus._jobs["j1"]
    assert state.dispatcher is not None
    state.dispatcher.cancel()

    await bus.publish(_ev("j1", 0))
    await bus.publish(_ev("j1", 1))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bus.publish(_ev("j1", 2)), timeout=0.05)
