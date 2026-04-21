"""Unit tests for convert_endpoint_file service function."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.service import convert_endpoint_file

_MINIMAL_OAS3 = {
    "openapi": "3.0.3",
    "info": {"title": "T", "version": "1"},
    "paths": {},
}


class TestConvertEndpointFile:
    def test_nonexistent_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConverterError, match="does not exist"):
            convert_endpoint_file(
                tmp_path / "missing.json",
                tmp_path / "out",
                tmp_path / "orig",
            )

    def test_copies_source_to_originals_dir(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        orig_dir = tmp_path / "originals"
        out_dir = tmp_path / "out"
        convert_endpoint_file(src, out_dir, orig_dir)
        assert (orig_dir / "spec.json").exists()

    def test_validate_called_before_convert(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        calls: list[str] = []
        adapter = MagicMock()
        adapter.validate.side_effect = lambda _: calls.append("validate")
        adapter.convert.side_effect = lambda s, o: (
            calls.append("convert") or (o / "seed.json")
        )
        with patch(
            "infrastructure.endpoints.converters.service.FormatDetector"
        ) as MockDetector:
            MockDetector.return_value.detect.return_value = "oas3"
            with patch(
                "infrastructure.endpoints.converters.service._ADAPTER_MAP",
                {"oas3": lambda: adapter},
            ):
                convert_endpoint_file(src, tmp_path / "out", tmp_path / "orig")
        assert calls == ["validate", "convert"]

    def test_returns_path_from_convert(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        expected = tmp_path / "out" / "seed.json"
        adapter = MagicMock()
        adapter.validate.return_value = None
        adapter.convert.return_value = expected
        with patch(
            "infrastructure.endpoints.converters.service.FormatDetector"
        ) as MockDetector:
            MockDetector.return_value.detect.return_value = "oas3"
            with patch(
                "infrastructure.endpoints.converters.service._ADAPTER_MAP",
                {"oas3": lambda: adapter},
            ):
                result = convert_endpoint_file(src, tmp_path / "out", tmp_path / "orig")
        assert result == expected

    def test_converter_error_from_detector_propagates(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        with pytest.raises(ConverterError):
            convert_endpoint_file(src, tmp_path / "out", tmp_path / "orig")

    def test_converter_error_from_adapter_propagates(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        adapter = MagicMock()
        adapter.validate.side_effect = ConverterError("bad file")
        with patch(
            "infrastructure.endpoints.converters.service.FormatDetector"
        ) as MockDetector:
            MockDetector.return_value.detect.return_value = "oas3"
            with patch(
                "infrastructure.endpoints.converters.service._ADAPTER_MAP",
                {"oas3": lambda: adapter},
            ):
                with pytest.raises(ConverterError, match="bad file"):
                    convert_endpoint_file(src, tmp_path / "out", tmp_path / "orig")
