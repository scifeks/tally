"""Unit tests for FormatDetector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.detector import FormatDetector

_OAS3_DOC = {
    "openapi": "3.0.3",
    "info": {"title": "T", "version": "1"},
    "paths": {},
}
_OAS2_DOC = {"swagger": "2.0", "info": {"title": "T", "version": "1"}}
_POSTMAN_DOC = {
    "info": {
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    }
}
_POSTMAN_V20_DOC = {
    "info": {
        "schema": "https://schema.getpostman.com/json/collection/v2.0.0/collection.json"
    }
}


class TestFormatDetector:
    def test_har_extension_returns_har_without_parsing(self, tmp_path: Path) -> None:
        f = tmp_path / "traffic.har"
        f.write_text("{}", encoding="utf-8")
        assert FormatDetector().detect(f) == "har"

    def test_oas3_json_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(_OAS3_DOC), encoding="utf-8")
        assert FormatDetector().detect(f) == "oas3"

    def test_oas2_json_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "swagger.json"
        f.write_text(json.dumps(_OAS2_DOC), encoding="utf-8")
        assert FormatDetector().detect(f) == "oas2"

    def test_postman_json_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "collection.json"
        f.write_text(json.dumps(_POSTMAN_DOC), encoding="utf-8")
        assert FormatDetector().detect(f) == "postman"

    def test_postman_v20_json_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "collection_v20.json"
        f.write_text(json.dumps(_POSTMAN_V20_DOC), encoding="utf-8")
        assert FormatDetector().detect(f) == "postman"

    def test_unrecognized_json_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "unknown.json"
        f.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        with pytest.raises(ConverterError):
            FormatDetector().detect(f)

    def test_unparseable_file_raises(self, tmp_path: Path) -> None:
        f = tmp_path / "broken.json"
        f.write_text("{not valid json}", encoding="utf-8")
        with pytest.raises(ConverterError):
            FormatDetector().detect(f)
