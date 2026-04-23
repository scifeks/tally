"""Unit tests for SessionAuthMiddleware."""

from __future__ import annotations

import httpx
from fastapi import FastAPI, Request

from web.auth.sessions import SessionStore
from web.middleware.session_auth import SessionAuthMiddleware

_PORT = 8080


def _app() -> tuple[FastAPI, SessionStore]:
    store = SessionStore()
    app = FastAPI()
    app.state.session_store = store
    app.add_middleware(SessionAuthMiddleware)

    @app.get("/api/protected")
    async def protected(req: Request) -> dict[str, str]:
        return {"session_id": req.state.session_id}

    @app.post("/api/auth/exchange")
    async def exchange() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/auth/me")
    async def me() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/public")
    async def public() -> dict[str, bool]:
        return {"ok": True}

    return app, store


async def test_non_api_path_skips_auth() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/public")
    assert resp.status_code == 200


async def test_exchange_path_is_exempt() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/auth/exchange")
    assert resp.status_code == 200


async def test_me_path_is_exempt() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/api/auth/me")
    assert resp.status_code == 200


async def test_missing_cookie_returns_401() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/api/protected")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_invalid_session_id_returns_401() -> None:
    app, _ = _app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        c.cookies.set("tally_session", "not-a-real-session")
        resp = await c.get("/api/protected")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


async def test_valid_session_passes_and_sets_state() -> None:
    app, store = _app()
    session_id, _ = store.create()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        c.cookies.set("tally_session", session_id)
        resp = await c.get("/api/protected")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == session_id
