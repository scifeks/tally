"""Unit tests for CORSMiddleware installation in create_app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.server import create_app

_PORT = 8765
_TOKEN = "testtoken"
_VITE_ORIGIN = "http://127.0.0.1:3000"
_EVIL_ORIGIN = "http://evil.example.com"


def _client(allowed_origins: list[str] | None = None) -> TestClient:
    app = create_app(
        base_path="/tmp/tally_cors_test",
        handshake_token=_TOKEN,
        port=_PORT,
        allowed_origins=allowed_origins,
    )
    return TestClient(app, raise_server_exceptions=False)


class TestCorsNotInstalled:
    def test_preflight_has_no_cors_headers_when_no_origins_configured(self) -> None:
        client = _client(allowed_origins=None)
        resp = client.options(
            "/api/v1/findings",
            headers={
                "Origin": _VITE_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers

    def test_preflight_has_no_cors_headers_when_empty_origins_list(self) -> None:
        client = _client(allowed_origins=[])
        resp = client.options(
            "/api/v1/findings",
            headers={
                "Origin": _VITE_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers


class TestCorsInstalled:
    @pytest.fixture()
    def client(self) -> TestClient:
        return _client(allowed_origins=[_VITE_ORIGIN])

    def test_preflight_from_configured_origin_returns_200(
        self, client: TestClient
    ) -> None:
        resp = client.options(
            "/api/v1/findings",
            headers={
                "Origin": _VITE_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == _VITE_ORIGIN

    def test_preflight_includes_credentials_header(self, client: TestClient) -> None:
        resp = client.options(
            "/api/v1/findings",
            headers={
                "Origin": _VITE_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-credentials") == "true"

    def test_preflight_from_unlisted_origin_has_no_allow_header(
        self, client: TestClient
    ) -> None:
        resp = client.options(
            "/api/v1/findings",
            headers={
                "Origin": _EVIL_ORIGIN,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in resp.headers

    def test_wildcard_never_in_allow_origin_header(self, client: TestClient) -> None:
        for origin in (_VITE_ORIGIN, _EVIL_ORIGIN):
            resp = client.options(
                "/api/v1/findings",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            allow = resp.headers.get("access-control-allow-origin", "")
            assert allow != "*", f"Wildcard CORS returned for origin {origin!r}"
