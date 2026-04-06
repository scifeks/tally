"""Unit tests for HARAdapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.har import HARAdapter

_EMPTY_HAR = {"log": {"entries": []}}


def _har_with_entries(entries: list) -> dict:
    return {"log": {"entries": entries}}


def _get_entry(
    path: str = "/api/test",
    method: str = "GET",
    query: list | None = None,
    post_data: dict | None = None,
    status: int = 200,
) -> dict:
    entry: dict = {
        "request": {
            "method": method,
            "url": f"https://example.com{path}",
            "queryString": query or [],
        },
        "response": {"status": status},
    }
    if post_data:
        entry["request"]["postData"] = post_data
    return entry


class TestHARAdapter:
    def test_missing_log_key_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "test.har"
        f.write_text(json.dumps({"entries": []}), encoding="utf-8")
        with pytest.raises(ConverterError, match="'log'"):
            HARAdapter().validate(f)

    def test_empty_entries_produces_empty_paths(self, tmp_path: Path) -> None:
        f = tmp_path / "test.har"
        f.write_text(json.dumps(_EMPTY_HAR), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = HARAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert doc["paths"] == {}

    def test_single_get_entry_produces_path_item(self, tmp_path: Path) -> None:
        entry = _get_entry(
            path="/items",
            method="GET",
            query=[{"name": "page", "value": "1"}],
        )
        f = tmp_path / "test.har"
        f.write_text(json.dumps(_har_with_entries([entry])), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = HARAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert "/items" in doc["paths"]
        op = doc["paths"]["/items"]["get"]
        assert len(op["parameters"]) == 1
        assert op["parameters"][0]["name"] == "page"

    def test_post_entry_with_post_data_produces_request_body(
        self, tmp_path: Path
    ) -> None:
        entry = _get_entry(
            path="/submit",
            method="POST",
            post_data={
                "mimeType": "application/json",
                "text": '{"key": "val"}',
            },
        )
        f = tmp_path / "test.har"
        f.write_text(json.dumps(_har_with_entries([entry])), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = HARAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        op = doc["paths"]["/submit"]["post"]
        assert "requestBody" in op
        assert "application/json" in op["requestBody"]["content"]

    def test_duplicate_path_method_deduplicates_first_wins(
        self, tmp_path: Path
    ) -> None:
        entry1 = _get_entry("/dup", "GET", query=[{"name": "a", "value": "1"}])
        entry2 = _get_entry("/dup", "GET", query=[{"name": "b", "value": "2"}])
        f = tmp_path / "test.har"
        f.write_text(
            json.dumps(_har_with_entries([entry1, entry2])),
            encoding="utf-8",
        )
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = HARAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        params = doc["paths"]["/dup"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "a"

    def test_output_is_valid_json_with_openapi_key(self, tmp_path: Path) -> None:
        f = tmp_path / "test.har"
        f.write_text(json.dumps(_EMPTY_HAR), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = HARAdapter().convert(f, out_dir)
        doc = json.loads(result.read_text(encoding="utf-8"))
        assert "openapi" in doc
        assert doc["openapi"] == "3.0.3"
