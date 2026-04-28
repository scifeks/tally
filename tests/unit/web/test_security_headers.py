"""Unit tests for SecurityHeadersMiddleware."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from web.server import create_app

_PORT = 8765
_TOKEN = "testtoken"


@pytest.fixture()
def client() -> TestClient:
    app = create_app(
        base_path="/tmp/tally_secheaders_test",
        handshake_token=_TOKEN,
        port=_PORT,
        allowed_origins=None,
    )
    return TestClient(app, raise_server_exceptions=False)


class TestSecurityHeadersOnSuccessResponse:
    """Headers attach to a normal /api/* response."""

    def test_csp_header_present(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert "content-security-policy" in resp.headers

    def test_csp_omits_unsafe_inline(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        csp = resp.headers["content-security-policy"]
        assert "'unsafe-inline'" not in csp
        assert "'unsafe-eval'" not in csp

    def test_csp_includes_frame_ancestors_none(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert "frame-ancestors 'none'" in resp.headers["content-security-policy"]

    def test_x_frame_options_deny(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_x_content_type_options_nosniff(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_referrer_policy_no_referrer(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert resp.headers.get("referrer-policy") == "no-referrer"


class TestSecurityHeadersOnRejection:
    """Headers also attach when an inner middleware short-circuits."""

    def test_headers_present_on_invalid_host_400(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/health",
            headers={"host": "evil.example.com:9999"},
        )
        assert resp.status_code == 400
        assert "content-security-policy" in resp.headers
        assert resp.headers.get("x-frame-options") == "DENY"

    def test_headers_present_on_unauthenticated_401(self, client: TestClient) -> None:
        # Project endpoints require a session; with no cookie we get 401.
        resp = client.get(
            "/api/v1/projects",
            headers={"host": f"127.0.0.1:{_PORT}"},
        )
        assert resp.status_code == 401
        assert "content-security-policy" in resp.headers
        assert resp.headers.get("referrer-policy") == "no-referrer"
