"""Unit tests for OAS2Adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.oas2 import OAS2Adapter

_SWAGGER_DOC = {"swagger": "2.0", "info": {"title": "T", "version": "1"}}


class TestOAS2Adapter:
    def test_swagger_20_passes_validate(self, tmp_path: Path) -> None:
        f = tmp_path / "swagger.json"
        f.write_text(json.dumps(_SWAGGER_DOC), encoding="utf-8")
        OAS2Adapter().validate(f)  # must not raise

    def test_missing_swagger_key_raises(self, tmp_path: Path) -> None:
        doc = {"openapi": "3.0.3", "info": {"title": "T", "version": "1"}}
        f = tmp_path / "spec.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ConverterError):
            OAS2Adapter().validate(f)

    def test_convert_raises_when_npx_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "swagger.json"
        src.write_text(json.dumps(_SWAGGER_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        with patch(
            "infrastructure.endpoints.converters.oas2.shutil.which",
            return_value=None,
        ):
            with pytest.raises(ConverterError, match="Node.js"):
                OAS2Adapter().convert(src, out_dir)

    def test_convert_raises_on_nonzero_returncode(self, tmp_path: Path) -> None:
        src = tmp_path / "swagger.json"
        src.write_text(json.dumps(_SWAGGER_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "conversion failed"
        with patch(
            "infrastructure.endpoints.converters.oas2.shutil.which",
            return_value="/usr/bin/npx",
        ):
            with patch(
                "infrastructure.endpoints.converters.oas2.subprocess.run",
                return_value=mock_result,
            ):
                with pytest.raises(ConverterError, match="conversion failed"):
                    OAS2Adapter().convert(src, out_dir)

    def test_convert_returns_correct_path_on_success(self, tmp_path: Path) -> None:
        src = tmp_path / "swagger.json"
        src.write_text(json.dumps(_SWAGGER_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch(
            "infrastructure.endpoints.converters.oas2.shutil.which",
            return_value="/usr/bin/npx",
        ):
            with patch(
                "infrastructure.endpoints.converters.oas2.subprocess.run",
                return_value=mock_result,
            ):
                result = OAS2Adapter().convert(src, out_dir)
        assert result == out_dir / "endpoints.json"
