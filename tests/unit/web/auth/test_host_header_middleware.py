"""Unit tests for HostHeaderMiddleware."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from web.middleware.host_header import HostHeaderMiddleware

_PORT = 8080


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(HostHeaderMiddleware, port=_PORT)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_localhost_host_allowed() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://localhost:{_PORT}"
    ) as c:
        resp = await c.get("/ping")
    assert resp.status_code == 200


async def test_127_host_allowed() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/ping")
    assert resp.status_code == 200


async def test_unknown_host_rejected() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/ping", headers={"host": "evil.com"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_HOST"


async def test_wrong_port_rejected() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/ping", headers={"host": f"127.0.0.1:{_PORT + 1}"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_HOST"


async def test_empty_host_rejected() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/ping", headers={"host": ""})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_HOST"
