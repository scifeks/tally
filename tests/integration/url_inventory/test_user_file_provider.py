"""Integration tests for UserFileProvider."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.url_inventory.ports import UrlProviderContext  # noqa: E402
from application.url_inventory.providers.user_file import (  # noqa: E402
    UserFileProvider,
)
from core.config.schemas import Repository  # noqa: E402
from core.config.schemas.repo_service import RepoService  # noqa: E402
from domain.url_inventory.entry import UrlSource  # noqa: E402
from infrastructure.endpoints.converters.endpoint_file_converter import (  # noqa: E402
    EndpointFileConverter,
)

pytestmark = pytest.mark.integration


def _make_repo(tmp_path: Path, *, base_urls: list[str] | None = None) -> Repository:
    """Build a minimal Repository for the provider context."""
    repo_path = tmp_path / "repo-src"
    repo_path.mkdir(exist_ok=True)
    service = RepoService.model_construct(
        name="default",
        relative_path="",
        type=["api"],
        languages=["python"],
        base_urls=base_urls or [],
    )
    return Repository(
        name="alpha",
        path=str(repo_path),
        services=[service],
    )


def _ctx(tmp_path: Path, *, base_urls: list[str] | None = None) -> UrlProviderContext:
    return UrlProviderContext(
        repo=_make_repo(tmp_path, base_urls=base_urls),
        repo_id=1,
        base_path=str(tmp_path),
        project_name="alpha",
        run_id=None,
    )


def _write_oas3(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


_MIN_OAS3: dict = {
    "openapi": "3.0.0",
    "info": {"title": "test", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/api/users": {
            "get": {"responses": {"200": {"description": "ok"}}},
            "post": {"responses": {"201": {"description": "created"}}},
        },
        "/api/orders": {
            "get": {
                "parameters": [
                    {
                        "name": "id",
                        "in": "query",
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"description": "ok"}},
            }
        },
    },
}


class TestProvideOAS3:
    def test_yields_one_row_per_method(self, tmp_path: Path) -> None:
        spec = _write_oas3(tmp_path, _MIN_OAS3)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        # 2 methods on /api/users + 1 on /api/orders = 3.
        assert len(rows) == 3
        triples = sorted((r.method, r.path) for r in rows)
        assert triples == [
            ("GET", "/api/orders"),
            ("GET", "/api/users"),
            ("POST", "/api/users"),
        ]

    def test_all_rows_are_user_source(self, tmp_path: Path) -> None:
        spec = _write_oas3(tmp_path, _MIN_OAS3)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        assert all(r.source is UrlSource.USER for r in rows)
        assert all(r.tool is None for r in rows)
        assert all(r.run_id is None for r in rows)
        assert all(r.file_path == str(spec) for r in rows)

    def test_meta_carries_original_operation(self, tmp_path: Path) -> None:
        spec = _write_oas3(tmp_path, _MIN_OAS3)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        orders = next(r for r in rows if r.path == "/api/orders")
        assert "original_file" in orders.meta
        assert orders.meta["original_file"]["parameters"][0]["name"] == "id"

    def test_repo_id_carried_through(self, tmp_path: Path) -> None:
        spec = _write_oas3(tmp_path, _MIN_OAS3)
        ctx = UrlProviderContext(
            repo=_make_repo(tmp_path),
            repo_id=42,
            base_path=str(tmp_path),
            project_name="alpha",
        )
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(ctx, file_path=str(spec))
        )
        assert all(r.repo_id == 42 for r in rows)


class TestBaseResolution:
    def test_uses_doc_servers_first(self, tmp_path: Path) -> None:
        doc = {**_MIN_OAS3, "servers": [{"url": "https://api.example.com:8443"}]}
        spec = _write_oas3(tmp_path, doc)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path, base_urls=["https://override.test"]),
                file_path=str(spec),
            )
        )
        assert rows[0].host == "api.example.com"
        assert rows[0].port == 8443
        assert rows[0].protocol == "https"

    def test_falls_back_to_repo_base_urls(self, tmp_path: Path) -> None:
        doc = {**_MIN_OAS3}
        doc.pop("servers", None)
        spec = _write_oas3(tmp_path, doc)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path, base_urls=["http://internal.test:8080"]),
                file_path=str(spec),
            )
        )
        assert rows[0].host == "internal.test"
        assert rows[0].protocol == "http"
        assert rows[0].port == 8080

    def test_default_port_https(self, tmp_path: Path) -> None:
        doc = {**_MIN_OAS3, "servers": [{"url": "https://www.example.com"}]}
        spec = _write_oas3(tmp_path, doc)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        assert rows[0].port == 443

    def test_default_port_http(self, tmp_path: Path) -> None:
        doc = {**_MIN_OAS3, "servers": [{"url": "http://www.example.com"}]}
        spec = _write_oas3(tmp_path, doc)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        assert rows[0].port == 80


class TestSkipsUnsupportedMethods:
    def test_skips_non_http_method_keys(self, tmp_path: Path) -> None:
        doc = {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/x": {
                    "get": {"responses": {"200": {"description": ""}}},
                    "summary": "this is OAS3 metadata, not a method",
                    "parameters": [],
                }
            },
        }
        spec = _write_oas3(tmp_path, doc)
        rows = list(
            UserFileProvider(EndpointFileConverter()).provide(
                _ctx(tmp_path), file_path=str(spec)
            )
        )
        # Only GET should produce a row; "summary" and "parameters" are
        # path-level OAS3 keys, not HTTP methods.
        assert {(r.method, r.path) for r in rows} == {("GET", "/x")}
