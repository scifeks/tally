"""Unit tests for CSRFMiddleware."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from web.auth.sessions import SessionStore
from web.middleware.csrf import CSRFMiddleware
from web.middleware.session_auth import SessionAuthMiddleware

_PORT = 8080


def _app() -> tuple[FastAPI, SessionStore]:
    store = SessionStore()
    app = FastAPI()
    app.state.session_store = store
    # CSRF innermost, SessionAuth outermost — mirrors production stack ordering.
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(SessionAuthMiddleware)

    @app.post("/api/action")
    async def action() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/data")
    async def data() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/v1/auth/exchange")
    async def exchange() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/public")
    async def public() -> dict[str, bool]:
        return {"ok": True}

    return app, store


async def _authed_client(
    app: FastAPI, store: SessionStore
) -> tuple[httpx.AsyncClient, str]:
    """Return (client, csrf_token) with tally_session cookie pre-injected."""
    session_id, csrf_token = store.create()
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    )
    client.cookies.set("tally_session", session_id)
    return client, csrf_token


async def test_get_passes_without_csrf_header() -> None:
    app, store = _app()
    async with (await _authed_client(app, store))[0] as c:
        resp = await c.get("/api/data")
    assert resp.status_code == 200


async def test_non_api_path_passes_without_csrf() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/public")
    assert resp.status_code == 200


async def test_exempt_path_passes_without_csrf() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/v1/auth/exchange")
    assert resp.status_code == 200


async def test_post_without_csrf_header_returns_403() -> None:
    app, store = _app()
    client, _ = await _authed_client(app, store)
    async with client as c:
        resp = await c.post("/api/action")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_post_with_wrong_csrf_returns_403() -> None:
    app, store = _app()
    client, _ = await _authed_client(app, store)
    async with client as c:
        resp = await c.post("/api/action", headers={"x-csrf-token": "wrong-token"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


async def test_post_with_correct_csrf_passes() -> None:
    app, store = _app()
    client, csrf_token = await _authed_client(app, store)
    async with client as c:
        resp = await c.post("/api/action", headers={"x-csrf-token": csrf_token})
    assert resp.status_code == 200
