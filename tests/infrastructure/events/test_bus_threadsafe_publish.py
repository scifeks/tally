import asyncio
import threading
from datetime import UTC, datetime

from infrastructure.events import EventBus
from infrastructure.events.types import BusEvent


def _ev(job_id: str) -> BusEvent:
    return BusEvent(
        event_id="evt1",
        job_id=job_id,
        stream="scan",
        event_type="log",
        payload={"from": "thread"},
        ts=datetime.now(tz=UTC),
    )


async def test_publish_threadsafe_from_repl_thread():
    bus = EventBus()
    await bus.register_job("j1", "scan")
    _, q = await bus.subscribe("j1")

    event = _ev("j1")

    def repl_thread() -> None:
        bus.publish_threadsafe(event)

    t = threading.Thread(target=repl_thread)
    t.start()

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: t.join(2.0))
    assert not t.is_alive()

    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received == event

    await bus.close_job("j1")
