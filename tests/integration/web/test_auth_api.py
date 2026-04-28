"""Integration tests for the auth endpoint: exchange."""

from __future__ import annotations

import pytest

from tests.integration.web.conftest import HANDSHAKE, TEST_PORT

pytestmark = pytest.mark.integration


class TestExchange:
    async def test_bad_token_returns_401(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        resp = await client.post(
            "/api/v1/auth/exchange",
            json={"token": "not-a-real-token"},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 401

    async def test_replay_token_returns_401(self, app_client) -> None:
        # HANDSHAKE was consumed by the fixture's _authenticate call.
        client, _, _, _, _, _ = app_client
        resp = await client.post(
            "/api/v1/auth/exchange",
            json={"token": HANDSHAKE},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 401

    async def test_good_token_returns_csrf_cookie(self, app_client) -> None:
        # The fixture already exchanged. Confirm the X-CSRF-Token header in
        # mut_headers (sourced from the cookie) is non-empty.
        _, _, _, _, mut_headers, _ = app_client
        assert mut_headers["X-CSRF-Token"]

    async def test_exchange_response_body_does_not_leak_csrf(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        # New handshake on a fresh registry entry to inspect the response body
        # directly. The fixture already consumed HANDSHAKE, so register a new
        # one for this assertion.
        registry = client._transport.app.state.handshake_registry
        registry.register("inspect-token-1")
        resp = await client.post(
            "/api/v1/auth/exchange",
            json={"token": "inspect-token-1"},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"ok": True}
        assert "csrf_token" not in body

    async def test_exchange_sets_session_cookie(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        assert client.cookies.get("tally_session") is not None

    async def test_exchange_sets_csrf_cookie(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        assert client.cookies.get("tally_csrf") is not None
