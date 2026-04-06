"""Unit tests for OAS3PassthroughAdapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.oas3 import OAS3PassthroughAdapter

_MINIMAL_OAS3 = {
    "openapi": "3.0.3",
    "info": {"title": "Test", "version": "1.0.0"},
    "paths": {},
}


class TestOAS3PassthroughAdapter:
    def test_valid_oas3_json_passes_validate(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        OAS3PassthroughAdapter().validate(f)  # must not raise

    def test_valid_oas3_yaml_passes_validate(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.yaml"
        f.write_text(yaml.dump(_MINIMAL_OAS3), encoding="utf-8")
        OAS3PassthroughAdapter().validate(f)  # must not raise

    def test_missing_openapi_key_raises(self, tmp_path: Path) -> None:
        doc = {"info": {"title": "X", "version": "1"}, "paths": {}}
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ConverterError):
            OAS3PassthroughAdapter().validate(f)

    def test_openapi_2_key_raises(self, tmp_path: Path) -> None:
        doc = {"openapi": "2.0", "info": {"title": "X", "version": "1"}}
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ConverterError):
            OAS3PassthroughAdapter().validate(f)

    def test_convert_json_copies_to_endpoints_json(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = OAS3PassthroughAdapter().convert(src, out_dir)
        assert result == out_dir / "endpoints.json"
        assert result.exists()

    def test_convert_yaml_copies_to_endpoints_yaml(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.yaml"
        src.write_text(yaml.dump(_MINIMAL_OAS3), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = OAS3PassthroughAdapter().convert(src, out_dir)
        assert result == out_dir / "endpoints.yaml"
        assert result.exists()
