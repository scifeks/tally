"""Unit tests for KatanaAdapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.katana import KatanaAdapter


def _katana_line(
    endpoint: str = "https://example.com/api/test",
    method: str = "GET",
    status_code: int = 200,
    content_type: str | None = "text/html",
    extra_request: dict | None = None,
) -> dict:
    headers: dict[str, str] = {}
    if content_type:
        headers["content-type"] = content_type
    record: dict = {
        "timestamp": "2026-01-01T00:00:00Z",
        "request": {
            "method": method,
            "endpoint": endpoint,
            "raw": f"{method} / HTTP/1.1\r\nHost: example.com\r\n\r\n",
        },
        "response": {
            "status_code": status_code,
            "headers": headers,
            "body": "",
            "content_length": 0,
        },
    }
    if extra_request:
        record["request"].update(extra_request)
    return record


def _jsonl_from_lines(lines: list[dict]) -> str:
    return "\n".join(json.dumps(ln) for ln in lines)


class TestKatanaAdapter:
    def test_empty_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "out.jsonl"
        f.write_text("", encoding="utf-8")
        with pytest.raises(ConverterError, match="no JSONL records"):
            KatanaAdapter().validate(f)

    def test_malformed_line_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "out.jsonl"
        f.write_text("not-json\n", encoding="utf-8")
        with pytest.raises(ConverterError, match="not valid JSON"):
            KatanaAdapter().validate(f)

    def test_missing_endpoint_field_raises(self, tmp_path: Path) -> None:
        bad = {"request": {"method": "GET"}, "response": {"status_code": 200}}
        f = tmp_path / "out.jsonl"
        f.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with pytest.raises(ConverterError, match="request.endpoint"):
            KatanaAdapter().validate(f)

    def test_valid_file_passes_validation(self, tmp_path: Path) -> None:
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([_katana_line()]) + "\n", encoding="utf-8")
        KatanaAdapter().validate(f)  # must not raise

    def test_single_get_produces_path_item(self, tmp_path: Path) -> None:
        line = _katana_line(
            endpoint="https://example.com/items?page=1&sort=asc",
            method="GET",
            status_code=200,
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert "/items" in doc["paths"]
        op = doc["paths"]["/items"]["get"]
        param_names = {p["name"] for p in op["parameters"]}
        assert "page" in param_names
        assert "sort" in param_names

    def test_output_envelope_has_openapi_3(self, tmp_path: Path) -> None:
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([_katana_line()]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert doc["openapi"] == "3.0.3"
        assert doc["info"]["title"] == "Imported from Katana"

    def test_duplicate_path_method_deduplicates_first_wins(
        self, tmp_path: Path
    ) -> None:
        line1 = _katana_line(
            endpoint="https://example.com/dup?a=1",
            method="GET",
            status_code=200,
        )
        line2 = _katana_line(
            endpoint="https://example.com/dup?b=2",
            method="GET",
            status_code=404,
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line1, line2]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/dup"]["get"]
        # First record wins; status 200, param 'a'
        assert "200" in op["responses"]
        param_names = {p["name"] for p in op["parameters"]}
        assert "a" in param_names
        assert "b" not in param_names

    def test_post_with_content_type_produces_request_body(self, tmp_path: Path) -> None:
        line = _katana_line(
            endpoint="https://example.com/submit",
            method="POST",
            status_code=201,
            content_type="application/json",
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/submit"]["post"]
        assert "requestBody" in op
        assert "application/json" in op["requestBody"]["content"]

    def test_status_code_in_responses(self, tmp_path: Path) -> None:
        line = _katana_line(
            endpoint="https://example.com/resource",
            method="GET",
            status_code=302,
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/resource"]["get"]
        assert "302" in op["responses"]

    def test_content_type_in_response_object(self, tmp_path: Path) -> None:
        line = _katana_line(
            endpoint="https://example.com/api",
            method="GET",
            status_code=200,
            content_type="application/json",
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/api"]["get"]
        resp = op["responses"]["200"]
        assert "content" in resp
        assert "application/json" in resp["content"]

    def test_multiple_paths_all_present(self, tmp_path: Path) -> None:
        lines = [
            _katana_line(endpoint="https://example.com/a"),
            _katana_line(endpoint="https://example.com/b", method="POST"),
        ]
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines(lines) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert "/a" in doc["paths"]
        assert "/b" in doc["paths"]

    def test_get_does_not_get_request_body(self, tmp_path: Path) -> None:
        line = _katana_line(
            endpoint="https://example.com/read",
            method="GET",
            content_type="application/json",
        )
        f = tmp_path / "out.jsonl"
        f.write_text(_jsonl_from_lines([line]) + "\n", encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = KatanaAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/read"]["get"]
        assert "requestBody" not in op
