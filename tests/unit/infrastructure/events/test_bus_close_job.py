import asyncio
from datetime import UTC, datetime

import pytest

from infrastructure.events import EventBus
from infrastructure.events.exceptions import UnknownJob
from infrastructure.events.types import EOS, BusEvent


def _ev(job_id: str) -> BusEvent:
    return BusEvent(
        event_id="evt1",
        job_id=job_id,
        stream="scan",
        event_type="log",
        payload={},
        ts=datetime.now(tz=UTC),
    )


async def test_close_job_enqueues_eos_to_subscriber():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    _, q = await bus.subscribe("j1")

    await bus.close_job("j1")

    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert item is EOS


async def test_close_job_removes_job_state():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    await bus.close_job("j1")

    await asyncio.sleep(0.05)

    with pytest.raises(UnknownJob):
        await bus.publish(_ev("j1"))


async def test_close_unknown_job_raises():
    bus = EventBus()
    with pytest.raises(UnknownJob):
        await bus.close_job("nonexistent")
