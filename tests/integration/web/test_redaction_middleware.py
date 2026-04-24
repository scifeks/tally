"""Integration tests for RedactionMiddleware."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, StreamingResponse
from starlette.requests import Request
from starlette.responses import Response
from starlette.testclient import TestClient

from web.api._redact import REDACTED, install_redaction_middleware, redact_exempt

pytestmark = pytest.mark.integration

_SENSITIVE_DICT = {"api_key": "secret", "model": "opus"}
_HEADERS_DICT = {"katana_headers": {"Cookie": "session=abc", "User-Agent": "bot"}}
_URL_DICT = {"login_url": "https://x.example/?token=abc&page=2"}


def _make_app() -> FastAPI:
    app = FastAPI()
    install_redaction_middleware(app)

    @app.get("/sensitive-dict")
    async def sensitive_dict() -> dict:
        return _SENSITIVE_DICT

    @app.get("/sensitive-list")
    async def sensitive_list() -> list:
        return [_SENSITIVE_DICT, {"model": "sonnet"}]

    @app.get("/sensitive-headers")
    async def sensitive_headers() -> dict:
        return _HEADERS_DICT

    @app.get("/sensitive-url")
    async def sensitive_url() -> dict:
        return _URL_DICT

    @app.get("/exempt")
    @redact_exempt  # safe: returns only non-sensitive field-spec metadata
    async def exempt_route() -> dict:
        return _SENSITIVE_DICT

    @app.patch("/echo")
    async def echo(request: Request) -> dict:
        return await request.json()

    @app.get("/plain-text")
    async def plain_text() -> PlainTextResponse:
        return PlainTextResponse("api_key=secret")

    @app.get("/sse")
    async def sse() -> StreamingResponse:
        async def gen() -> AsyncGenerator[bytes]:
            yield b'data: {"api_key": "secret"}\n\n'

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/malformed-json")
    async def malformed_json() -> Response:
        return Response(content=b"{bad json", media_type="application/json")

    return app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient]:
    with TestClient(_make_app(), raise_server_exceptions=False) as c:
        yield c


def test_dict_api_key_redacted(client: TestClient) -> None:
    resp = client.get("/sensitive-dict")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == REDACTED
    assert body["model"] == "opus"


def test_list_of_dicts_redacted(client: TestClient) -> None:
    resp = client.get("/sensitive-list")
    assert resp.status_code == 200
    items = resp.json()
    assert items[0]["api_key"] == REDACTED
    assert items[1]["model"] == "sonnet"


def test_headers_dict_redacted(client: TestClient) -> None:
    resp = client.get("/sensitive-headers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["katana_headers"]["Cookie"] == REDACTED
    assert body["katana_headers"]["User-Agent"] == "bot"


def test_url_param_redacted(client: TestClient) -> None:
    from urllib.parse import parse_qsl, urlsplit

    resp = client.get("/sensitive-url")
    assert resp.status_code == 200
    url = resp.json()["login_url"]
    params = dict(parse_qsl(urlsplit(url).query))
    assert params["token"] == REDACTED
    assert params["page"] == "2"


def test_redact_exempt_route_passes_through_unchanged(client: TestClient) -> None:
    resp = client.get("/exempt")
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == "secret"


def test_patch_body_not_scrubbed(client: TestClient) -> None:
    resp = client.patch("/echo", json={"api_key": "secret", "model": "opus"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == "secret"


def test_plain_text_response_not_touched(client: TestClient) -> None:
    resp = client.get("/plain-text")
    assert resp.status_code == 200
    assert resp.text == "api_key=secret"
    assert REDACTED not in resp.text


def test_sse_stream_not_mutated(client: TestClient) -> None:
    resp = client.get("/sse")
    assert resp.status_code == 200
    assert b"api_key" in resp.content
    assert REDACTED.encode() not in resp.content


def test_malformed_json_passed_through_with_warning(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="tally.web.redact"):
        resp = client.get("/malformed-json")
    assert resp.status_code == 200
    assert resp.content == b"{bad json"
    assert any("failed to parse" in r.message for r in caplog.records)
