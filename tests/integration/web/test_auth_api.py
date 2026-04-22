"""Integration tests for the auth endpoints: exchange, me, logout."""

from __future__ import annotations

import pytest

from tests.integration.web.conftest import HANDSHAKE, TEST_PORT

pytestmark = pytest.mark.integration


class TestExchange:
    async def test_bad_token_returns_401(self, app_client) -> None:
        client, _, _, _, _ = app_client
        resp = await client.post(
            "/api/auth/exchange",
            json={"token": "not-a-real-token"},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 401

    async def test_replay_token_returns_401(self, app_client) -> None:
        # HANDSHAKE was consumed by the fixture's _authenticate call.
        client, _, _, _, _ = app_client
        resp = await client.post(
            "/api/auth/exchange",
            json={"token": HANDSHAKE},
            headers={"origin": f"http://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 401

    async def test_good_token_returns_csrf_token(self, app_client) -> None:
        # The fixture already exchanged and captured the csrf_token in
        # mut_headers — confirm it is a non-empty string.
        _, _, _, _, mut_headers = app_client
        assert mut_headers["X-CSRF-Token"]

    async def test_exchange_sets_session_cookie(self, app_client) -> None:
        client, _, _, _, _ = app_client
        assert client.cookies.get("tally_session") is not None

    async def test_exchange_sets_csrf_cookie(self, app_client) -> None:
        client, _, _, _, _ = app_client
        assert client.cookies.get("tally_csrf") is not None


class TestMe:
    async def test_authenticated_returns_200(self, app_client) -> None:
        client, _, _, _, _ = app_client
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert "session_id" in data

    async def test_unauthenticated_returns_401(self, app_client) -> None:
        client, _, _, _, _ = app_client
        # /api/auth/me is exempt from SessionAuthMiddleware but handles auth
        # itself — a fresh client with no cookies gets 401.
        import httpx

        transport = client._transport
        async with httpx.AsyncClient(
            transport=transport,
            base_url=f"http://127.0.0.1:{TEST_PORT}",
        ) as fresh:
            resp = await fresh.get("/api/auth/me")
        assert resp.status_code == 401


class TestLogout:
    async def test_logout_returns_204(self, app_client) -> None:
        client, _, _, _, mut_headers = app_client
        resp = await client.post("/api/auth/logout", headers=mut_headers)
        assert resp.status_code == 204

    async def test_post_logout_protected_route_returns_401(self, app_client) -> None:
        client, _, _, _, mut_headers = app_client
        await client.post("/api/auth/logout", headers=mut_headers)
        # Session is revoked; subsequent /api/* calls must be rejected.
        resp = await client.get("/api/findings/")
        assert resp.status_code == 401

    async def test_post_logout_me_returns_401(self, app_client) -> None:
        client, _, _, _, mut_headers = app_client
        await client.post("/api/auth/logout", headers=mut_headers)
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401
