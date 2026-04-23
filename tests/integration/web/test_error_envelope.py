"""Integration tests for the canonical error envelope."""

from __future__ import annotations

import re
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.testclient import TestClient

from web.api._errors import (
    Conflict,
    Forbidden,
    NotFound,
    PathTraversal,
    Unauthenticated,
    ValidationError,
    install_error_handlers,
)

pytestmark = pytest.mark.integration


class _Body(BaseModel):
    value: int


def _make_app() -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/not-found")
    async def _not_found() -> dict:  # type: ignore[return]
        raise NotFound("thing not found")

    @app.get("/conflict")
    async def _conflict() -> dict:  # type: ignore[return]
        raise Conflict("already exists")

    @app.get("/validation-error")
    async def _api_validation() -> dict:  # type: ignore[return]
        raise ValidationError("bad value")

    @app.get("/path-traversal")
    async def _path_traversal() -> dict:  # type: ignore[return]
        raise PathTraversal("bad path")

    @app.get("/forbidden")
    async def _forbidden() -> dict:  # type: ignore[return]
        raise Forbidden("not allowed")

    @app.get("/unauthenticated")
    async def _unauthenticated() -> dict:  # type: ignore[return]
        raise Unauthenticated("login required")

    @app.get("/value-error")
    async def _value_error() -> dict:  # type: ignore[return]
        raise ValueError("bad input")

    @app.get("/file-not-found")
    async def _file_not_found() -> dict:  # type: ignore[return]
        raise FileNotFoundError("no such file")

    @app.get("/server-error")
    async def _server_error() -> dict:  # type: ignore[return]
        raise RuntimeError("unexpected crash")

    @app.get("/http-exception")
    async def _http_exception() -> dict:  # type: ignore[return]
        raise StarletteHTTPException(status_code=418, detail="I'm a teapot")

    @app.post("/request-validation")
    async def _request_validation(body: _Body) -> dict:
        return {"value": body.value}

    return app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(_make_app(), raise_server_exceptions=False) as c:
        yield c


def test_not_found(client: TestClient) -> None:
    resp = client.get("/not-found")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_conflict(client: TestClient) -> None:
    resp = client.get("/conflict")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_api_validation_error(client: TestClient) -> None:
    resp = client.get("/validation-error")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_path_traversal(client: TestClient) -> None:
    resp = client.get("/path-traversal")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PATH_TRAVERSAL"


def test_forbidden(client: TestClient) -> None:
    resp = client.get("/forbidden")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_unauthenticated(client: TestClient) -> None:
    resp = client.get("/unauthenticated")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHENTICATED"


def test_value_error(client: TestClient) -> None:
    resp = client.get("/value-error")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_file_not_found(client: TestClient) -> None:
    resp = client.get("/file-not-found")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_server_error(client: TestClient) -> None:
    resp = client.get("/server-error")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "SERVER_ERROR"
    body_str = str(body)
    assert "Traceback" not in body_str
    assert "raceback (most" not in body_str
    request_id = body["error"]["details"].get("request_id", "")
    assert re.fullmatch(r"[0-9a-f]{8}", request_id)


def test_http_exception_passthrough(client: TestClient) -> None:
    resp = client.get("/http-exception")
    assert resp.status_code == 418
    body = resp.json()
    assert "detail" in body
    assert "error" not in body


def test_request_validation_error_shape(client: TestClient) -> None:
    resp = client.post("/request-validation", json={"value": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = body["error"]["details"]["fields"]
    assert len(fields) > 0
    field = fields[0]
    assert "field" in field
    assert "type" in field
    assert "message" in field
    assert "input" not in field
    assert "ctx" not in field
    assert "url" not in field
