from __future__ import annotations

import asyncio
from typing import Any

from infrastructure.events.exceptions import SubscriberClosed, UnknownJob
from infrastructure.events.ids import new_event_id
from infrastructure.events.types import EOS, BusEvent, SubscriberId, _EOSType

_DEFAULT_INPUT_SIZE = 256
_DEFAULT_SUBSCRIBER_SIZE = 64

type _QueueItem = BusEvent | _EOSType


class _JobState:
    def __init__(
        self,
        job_id: str,
        stream: str,
        loop: asyncio.AbstractEventLoop,
        input_size: int,
        subscriber_size: int,
    ) -> None:
        self.job_id = job_id
        self.stream = stream
        self.loop = loop
        self.input_queue: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=input_size)
        self.subscriber_size = subscriber_size
        self.subscribers: dict[SubscriberId, asyncio.Queue[_QueueItem]] = {}
        self.closed = False
        self.dispatcher: asyncio.Task[None] | None = None


class EventBus:
    def __init__(self) -> None:
        self._jobs: dict[str, _JobState] = {}

    async def register_job(
        self,
        job_id: str,
        stream: str,
        input_size: int = _DEFAULT_INPUT_SIZE,
        subscriber_size: int = _DEFAULT_SUBSCRIBER_SIZE,
    ) -> None:
        if job_id in self._jobs and not self._jobs[job_id].closed:
            return
        loop = asyncio.get_running_loop()
        state = _JobState(job_id, stream, loop, input_size, subscriber_size)
        self._jobs[job_id] = state
        state.dispatcher = asyncio.create_task(
            self._dispatch(state), name=f"bus-{job_id}"
        )

    async def _dispatch(self, state: _JobState) -> None:
        while True:
            item = await state.input_queue.get()
            for q in list(state.subscribers.values()):
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    q.put_nowait(item)
            if item is EOS:
                break
        self._jobs.pop(state.job_id, None)

    async def publish(self, event: BusEvent) -> None:
        state = self._get_state(event.job_id)
        await state.input_queue.put(event)

    def publish_threadsafe(self, event: BusEvent) -> None:
        state = self._get_state(event.job_id)
        asyncio.run_coroutine_threadsafe(state.input_queue.put(event), state.loop)

    async def subscribe(
        self, job_id: str
    ) -> tuple[SubscriberId, asyncio.Queue[_QueueItem]]:
        state = self._get_state(job_id)
        if state.closed:
            raise SubscriberClosed(job_id)
        sub_id = SubscriberId(new_event_id())
        q: asyncio.Queue[_QueueItem] = asyncio.Queue(maxsize=state.subscriber_size)
        state.subscribers[sub_id] = q
        return sub_id, q

    async def unsubscribe(self, job_id: str, sub_id: SubscriberId) -> None:
        if job_id not in self._jobs:
            return
        self._jobs[job_id].subscribers.pop(sub_id, None)

    async def close_job(self, job_id: str) -> None:
        state = self._get_state(job_id)
        state.closed = True
        await state.input_queue.put(EOS)

    def _get_state(self, job_id: str) -> _JobState:
        if job_id not in self._jobs:
            raise UnknownJob(job_id)
        return self._jobs[job_id]

    def snapshot(self) -> dict[str, Any]:
        return {"jobs": dict(self._jobs)}

    def restore(self, state: dict[str, Any]) -> None:
        self._jobs = dict(state["jobs"])

    def reset(self) -> None:
        self._jobs = {}
