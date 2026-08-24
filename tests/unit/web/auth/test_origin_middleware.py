"""Unit tests for OriginCheckMiddleware."""

from __future__ import annotations

import httpx
from fastapi import FastAPI

from web.middleware.origin import OriginCheckMiddleware

_PORT = 8080
_ORIGIN = f"https://127.0.0.1:{_PORT}"


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware, port=_PORT)

    @app.get("/api/data")
    async def get_data() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/action")
    async def post_action() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/other/action")
    async def other_action() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_get_passes_without_origin() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.get("/api/data")
    assert resp.status_code == 200


async def test_post_with_matching_origin_passes() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/action", headers={"origin": _ORIGIN})
    assert resp.status_code == 200


async def test_post_without_origin_returns_403() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/action")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_post_with_cross_origin_returns_403() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/action", headers={"origin": "http://evil.com"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_post_with_referer_fallback_passes() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post(
            "/api/action",
            headers={"referer": f"{_ORIGIN}/some/page"},
        )
    assert resp.status_code == 200


async def test_non_api_path_skips_check() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/other/action")
    assert resp.status_code == 200


async def test_localhost_origin_allowed() -> None:
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post(
            "/api/action",
            headers={"origin": f"https://localhost:{_PORT}"},
        )
    assert resp.status_code == 200


_VITE_ORIGIN = "https://127.0.0.1:3000"


def _app_with_extra() -> FastAPI:
    app = FastAPI()
    app.add_middleware(OriginCheckMiddleware, port=_PORT, extra_origins=[_VITE_ORIGIN])

    @app.post("/api/action")
    async def post_action() -> dict[str, bool]:
        return {"ok": True}

    return app


async def test_extra_origin_accepted_for_post() -> None:
    transport = httpx.ASGITransport(app=_app_with_extra())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/action", headers={"origin": _VITE_ORIGIN})
    assert resp.status_code == 200


async def test_port_default_still_works_with_extra_origins() -> None:
    transport = httpx.ASGITransport(app=_app_with_extra())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post("/api/action", headers={"origin": _ORIGIN})
    assert resp.status_code == 200


async def test_unlisted_origin_rejected_even_with_extra_origins() -> None:
    transport = httpx.ASGITransport(app=_app_with_extra())
    async with httpx.AsyncClient(
        transport=transport, base_url=f"http://127.0.0.1:{_PORT}"
    ) as c:
        resp = await c.post(
            "/api/action", headers={"origin": "http://evil.example.com"}
        )
    assert resp.status_code == 403
