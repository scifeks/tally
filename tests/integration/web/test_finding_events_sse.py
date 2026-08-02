"""Integration tests for the finding event bus + SSE endpoint.

Verifies the publish contract: every successful PATCH (single or batch)
emits a ``finding_updated`` event on the ``finding`` stream with the
serialised finding plus ``project_id`` in the payload.

Tests subscribe to the EventBus directly rather than driving the SSE
stream over HTTP. ``httpx.AsyncClient`` with ``ASGITransport`` runs the
ASGI app inline on the test event loop, so a long-lived stream blocks
any concurrent PATCH on the same client. Subscribing to the bus tests
the same publish contract without that constraint; the SSE endpoint
itself is a thin wrapper around ``StreamingResponse`` that forwards
queue items via ``format_sse_frame``.
"""

from __future__ import annotations

import asyncio

import pytest

from infrastructure.events.bus import EventBus
from infrastructure.events.types import BusEvent
from tests.integration.web.conftest import TEST_PORT

pytestmark = pytest.mark.integration


def _events_url(project_id: int) -> str:
    return f"/api/v1/projects/{project_id}/findings/events"


def _bus_from(client) -> EventBus:
    """Reach the EventBus the test app was wired with."""
    return client._transport.app.state.event_bus


async def _next_event(queue: asyncio.Queue, *, timeout: float = 2.0) -> BusEvent:
    """Pop the next item and assert it is a BusEvent (not EOS)."""
    item = await asyncio.wait_for(queue.get(), timeout=timeout)
    assert isinstance(item, BusEvent)
    return item


class TestFindingEventsRouting:
    async def test_unknown_project_returns_404(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        resp = await client.get(
            _events_url(99999),
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 404


class TestFindingUpdatedPublished:
    async def test_single_patch_publishes_finding_updated(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        bus = _bus_from(client)
        sub_id, queue = await bus.subscribe("finding")
        try:
            resp = await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": "critical"},
                headers=mut_headers,
            )
            assert resp.status_code == 200

            event = await _next_event(queue)
            assert event.event_type == "finding_updated"
            assert event.stream == "finding"
            assert event.job_id == "finding"
            assert event.payload["project_id"] == project_id
            assert event.payload["id"] == finding_id
        finally:
            await bus.unsubscribe("finding", sub_id)

    async def test_payload_includes_serialised_finding_fields(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        bus = _bus_from(client)
        sub_id, queue = await bus.subscribe("finding")
        try:
            await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": "critical"},
                headers=mut_headers,
            )
            event = await _next_event(queue)
            payload = event.payload
            assert payload["severity"] == "critical"
            assert "is_locked" in payload
            assert "lock_holder" in payload
        finally:
            await bus.unsubscribe("finding", sub_id)

    async def test_batch_patch_publishes_event_per_updated_id(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        bus = _bus_from(client)
        sub_id, queue = await bus.subscribe("finding")
        try:
            resp = await client.patch(
                f"/api/v1/projects/{project_id}/findings/batch",
                json={"ids": [finding_id], "should_report": True},
                headers=mut_headers,
            )
            assert resp.status_code == 200

            event = await _next_event(queue)
            assert event.event_type == "finding_updated"
            assert event.payload["id"] == finding_id
            assert event.payload["project_id"] == project_id
        finally:
            await bus.unsubscribe("finding", sub_id)


class TestSubscriberFanout:
    async def test_two_subscribers_each_receive_the_event(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        bus = _bus_from(client)
        sub_a, queue_a = await bus.subscribe("finding")
        sub_b, queue_b = await bus.subscribe("finding")
        try:
            resp = await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": "critical"},
                headers=mut_headers,
            )
            assert resp.status_code == 200

            event_a = await _next_event(queue_a)
            event_b = await _next_event(queue_b)
            assert event_a.event_type == "finding_updated"
            assert event_b.event_type == "finding_updated"
            assert event_a.payload["id"] == finding_id
            assert event_b.payload["id"] == finding_id
        finally:
            await bus.unsubscribe("finding", sub_a)
            await bus.unsubscribe("finding", sub_b)

    async def test_unsubscribe_stops_event_delivery(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        bus = _bus_from(client)
        sub_id, queue = await bus.subscribe("finding")
        await bus.unsubscribe("finding", sub_id)

        await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "critical"},
            headers=mut_headers,
        )

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.5)
