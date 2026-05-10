"""Unit tests for AccessLogMiddleware (structured per-request logging)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.middleware.access_log import AccessLogMiddleware

_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def _ping() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/echo")
    def _echo(q: str | None = None, token: str | None = None) -> dict[str, str]:
        return {"q": q or "", "token": token or ""}

    @app.post("/submit")
    def _submit(payload: dict[str, str]) -> dict[str, str]:
        return {"echo": payload.get("api_key", "")}

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("boom")

    app.add_middleware(AccessLogMiddleware)
    return app


@pytest.fixture()
def log_file(tmp_path: Path) -> Generator[Path]:
    """Redirect ``tally.web.access`` to a temp file for the test's lifetime."""
    path = tmp_path / "web.log"
    handler = logging.FileHandler(path)
    handler.setFormatter(logging.Formatter("%(message)s"))
    access_logger = logging.getLogger("tally.web.access")
    previous_level = access_logger.level
    previous_propagate = access_logger.propagate
    access_logger.addHandler(handler)
    access_logger.setLevel(logging.INFO)
    access_logger.propagate = False
    try:
        yield path
    finally:
        access_logger.removeHandler(handler)
        handler.close()
        access_logger.setLevel(previous_level)
        access_logger.propagate = previous_propagate


@pytest.fixture()
def client() -> TestClient:
    return TestClient(_build_app(), raise_server_exceptions=False)


def _records(log_file: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in log_file.read_text().splitlines() if line.strip()
    ]


def _last_record(log_file: Path) -> dict[str, object]:
    records = _records(log_file)
    assert records, "expected at least one log record"
    return records[-1]


class TestHappyPath:
    def test_get_logs_method_path_status_latency_reqid(
        self, client: TestClient, log_file: Path
    ) -> None:
        resp = client.get("/ping")
        assert resp.status_code == 200

        rec = _last_record(log_file)
        assert rec["method"] == "GET"
        assert rec["path"] == "/ping"
        assert rec["status"] == 200
        assert isinstance(rec["latency_ms"], (int, float))
        assert rec["latency_ms"] >= 0
        assert isinstance(rec["req_id"], str)
        assert _HEX32.match(rec["req_id"])
        assert "error_class" not in rec

    def test_response_carries_matching_x_request_id_header(
        self, client: TestClient, log_file: Path
    ) -> None:
        resp = client.get("/ping")
        header_id = resp.headers.get("x-request-id")
        assert header_id is not None
        assert _HEX32.match(header_id)
        assert _last_record(log_file)["req_id"] == header_id

    def test_record_is_valid_json_with_expected_keys(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/ping")
        rec = _last_record(log_file)
        assert {"ts", "req_id", "method", "path", "status", "latency_ms"}.issubset(
            rec.keys()
        )


class TestQueryRedaction:
    def test_sensitive_param_value_redacted_others_preserved(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/echo?q=hello&token=secret-123")
        rec = _last_record(log_file)
        path = rec["path"]
        assert isinstance(path, str)
        assert path.startswith("/echo?")
        assert "token=%2A%2A%2AREDACTED%2A%2A%2A" in path or (
            "token=***REDACTED***" in path
        )
        assert "secret-123" not in path
        assert "q=hello" in path

    def test_non_sensitive_params_preserved(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/echo?q=hello")
        assert _last_record(log_file)["path"] == "/echo?q=hello"

    def test_empty_query_string_not_appended(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/ping")
        assert _last_record(log_file)["path"] == "/ping"


class TestErrorHandling:
    def test_exception_logs_error_class_and_5xx_status(
        self, client: TestClient, log_file: Path
    ) -> None:
        resp = client.get("/boom")
        assert resp.status_code >= 500

        rec = _last_record(log_file)
        assert rec["error_class"] == "RuntimeError"
        status = rec["status"]
        assert isinstance(status, int) and status >= 500
        assert rec["method"] == "GET"
        assert rec["path"] == "/boom"


class TestHeaderAndBodySafety:
    def test_request_body_never_logged(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.post("/submit", json={"api_key": "SECRET_BODY_VALUE"})
        assert "SECRET_BODY_VALUE" not in log_file.read_text()

    def test_authorization_header_never_logged(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/ping", headers={"Authorization": "Bearer SECRET_AUTH_VALUE"})
        assert "SECRET_AUTH_VALUE" not in log_file.read_text()

    def test_csrf_token_header_never_logged(
        self, client: TestClient, log_file: Path
    ) -> None:
        client.get("/ping", headers={"X-CSRF-Token": "SECRET_CSRF_VALUE"})
        assert "SECRET_CSRF_VALUE" not in log_file.read_text()

    def test_cookie_never_logged(self, client: TestClient, log_file: Path) -> None:
        client.cookies.set("session", "SECRET_COOKIE_VALUE")
        client.get("/ping")
        assert "SECRET_COOKIE_VALUE" not in log_file.read_text()


class TestRequestIdUniqueness:
    def test_each_request_gets_distinct_id(
        self, client: TestClient, log_file: Path
    ) -> None:
        for _ in range(10):
            client.get("/ping")
        ids = {rec["req_id"] for rec in _records(log_file)}
        assert len(ids) == 10
