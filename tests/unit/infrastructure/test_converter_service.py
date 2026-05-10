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

    def test_adapter_validates_and_converts_file(self, tmp_path: Path) -> None:
        src = tmp_path / "spec.json"
        src.write_text(json.dumps(_MINIMAL_OAS3), encoding="utf-8")
        adapter = MagicMock()
        out_file = tmp_path / "out" / "seed.json"
        adapter.convert.return_value = out_file
        with patch(
            "infrastructure.endpoints.converters.service.FormatDetector"
        ) as MockDetector:
            MockDetector.return_value.detect.return_value = "oas3"
            with patch(
                "infrastructure.endpoints.converters.service._ADAPTER_MAP",
                {"oas3": lambda: adapter},
            ):
                convert_endpoint_file(src, tmp_path / "out", tmp_path / "orig")
        adapter.validate.assert_called_once()
        adapter.convert.assert_called_once()

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
