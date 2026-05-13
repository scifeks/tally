"""Unit tests for application.url_inventory.artifact_builder (Phase 9 Step 3)."""

from __future__ import annotations

import json
from pathlib import Path

from application.url_inventory.artifact_builder import (
    build_oas3,
    build_seeds,
    write_artifacts,
)
from core.project_paths import ProjectPaths
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool


def _scan(
    *,
    method: str = "GET",
    protocol: str = "https",
    host: str = "api.example.com",
    port: int = 443,
    path: str = "/api/users",
    meta: dict | None = None,
) -> UrlFinding:
    return UrlFinding(
        repo_id=1,
        source=UrlSource.SCAN,
        tool=UrlTool.KATANA,
        run_id=None,
        method=method,
        protocol=protocol,
        host=host,
        port=port,
        path=path,
        meta=meta or {},
    )


class TestBuildSeeds:
    def test_default_https_port_omitted(self) -> None:
        out = build_seeds([_scan()])
        assert "https://api.example.com/api/users" in out
        assert ":443" not in out

    def test_default_http_port_omitted(self) -> None:
        out = build_seeds([_scan(protocol="http", port=80, host="x.test", path="/p")])
        assert "http://x.test/p" in out
        assert ":80" not in out

    def test_non_default_port_included(self) -> None:
        out = build_seeds([_scan(port=8443, path="/p")])
        assert "https://api.example.com:8443/p" in out

    def test_dedup_same_url(self) -> None:
        rows = [_scan(path="/dup"), _scan(path="/dup"), _scan(path="/other")]
        out = build_seeds(rows).strip().split("\n")
        assert sorted(out) == sorted(
            ["https://api.example.com/dup", "https://api.example.com/other"]
        )

    def test_query_params_from_oas3_meta(self) -> None:
        meta = {
            "original_file": {
                "parameters": [
                    {"in": "query", "name": "q", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
        out = build_seeds([_scan(path="/search", meta=meta)])
        assert "https://api.example.com/search?q=" in out

    def test_multiple_query_params(self) -> None:
        meta = {
            "original_file": {
                "parameters": [
                    {"in": "query", "name": "q", "schema": {"type": "string"}},
                    {"in": "query", "name": "page", "schema": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
        out = build_seeds([_scan(path="/search", meta=meta)])
        assert "?q=&page=" in out

    def test_non_query_params_excluded(self) -> None:
        meta = {
            "original_file": {
                "parameters": [
                    {"in": "path", "name": "id"},
                    {"in": "header", "name": "X-Token"},
                ],
                "responses": {"200": {"description": "ok"}},
            }
        }
        out = build_seeds([_scan(path="/items/{id}", meta=meta)])
        assert "?" not in out

    def test_no_meta_produces_bare_url(self) -> None:
        out = build_seeds([_scan(path="/plain")])
        assert "?" not in out

    def test_empty_input(self) -> None:
        assert build_seeds([]) == ""


class TestBuildOas3:
    def test_synthesizes_minimal_op_when_no_meta(self) -> None:
        doc = build_oas3([_scan(method="POST", path="/api/users")])
        assert "/api/users" in doc["paths"]
        assert "post" in doc["paths"]["/api/users"]
        op = doc["paths"]["/api/users"]["post"]
        assert "responses" in op

    def test_uses_meta_original_file_when_oas3_op(self) -> None:
        original = {
            "summary": "real",
            "parameters": [{"name": "id", "in": "query"}],
            "responses": {"200": {"description": "ok"}},
        }
        doc = build_oas3(
            [_scan(method="GET", path="/api/x", meta={"original_file": original})]
        )
        op = doc["paths"]["/api/x"]["get"]
        assert op["summary"] == "real"
        assert op["parameters"][0]["name"] == "id"

    def test_synthesizes_when_meta_lacks_oas3_keys(self) -> None:
        # meta.original_file present but not an OAS3 operation (e.g. HAR
        # entry); should fall back to synthesised stub.
        doc = build_oas3(
            [_scan(method="GET", path="/p", meta={"original_file": {"har": True}})]
        )
        assert "har" not in doc["paths"]["/p"]["get"]
        assert "responses" in doc["paths"]["/p"]["get"]

    def test_servers_url_from_first_row(self) -> None:
        doc = build_oas3([_scan(host="api.test.com", port=443)])
        assert doc["servers"][0]["url"] == "https://api.test.com"

    def test_servers_url_with_explicit_base(self) -> None:
        doc = build_oas3([_scan()], base_url="https://override.example/")
        assert doc["servers"][0]["url"] == "https://override.example/"

    def test_no_servers_when_empty(self) -> None:
        doc = build_oas3([])
        assert "servers" not in doc

    def test_multiple_methods_on_same_path(self) -> None:
        doc = build_oas3(
            [
                _scan(method="GET", path="/x"),
                _scan(method="POST", path="/x"),
            ]
        )
        assert set(doc["paths"]["/x"].keys()) == {"get", "post"}


class TestWriteArtifacts:
    def test_writes_both_files(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path / "proj")
        seeds, oas3 = write_artifacts(
            paths,
            "uuid-key",
            [_scan(path="/a"), _scan(path="/b", method="POST")],
        )
        assert Path(seeds).exists()
        assert Path(oas3).exists()
        assert "/a" in Path(seeds).read_text(encoding="utf-8")
        doc = json.loads(Path(oas3).read_text(encoding="utf-8"))
        assert "/a" in doc["paths"]
        assert "/b" in doc["paths"]

    def test_uses_repo_dir_key_in_path(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path / "proj")
        seeds, _ = write_artifacts(paths, "my-uuid-123", [_scan(path="/a")])
        assert "endpoints/my-uuid-123/merged_urls.txt" in seeds.replace("\\", "/")

    def test_overwrites_existing_atomically(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path / "proj")
        write_artifacts(paths, "u", [_scan(path="/old")])
        write_artifacts(paths, "u", [_scan(path="/new")])
        seeds_path = paths.endpoint_dir("u") / "merged_urls.txt"
        assert "/new" in seeds_path.read_text(encoding="utf-8")
        assert "/old" not in seeds_path.read_text(encoding="utf-8")
