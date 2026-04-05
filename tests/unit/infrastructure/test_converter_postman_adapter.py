"""Unit tests for PostmanAdapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.postman import PostmanAdapter

_POSTMAN_DOC = {
    "info": {
        "name": "My API",
        "schema": ("https://schema.getpostman.com/postman/collection/v2.1.0"),
    },
    "item": [],
}


class TestPostmanAdapter:
    def test_valid_postman_collection_passes_validate(self, tmp_path: Path) -> None:
        f = tmp_path / "col.json"
        f.write_text(json.dumps(_POSTMAN_DOC), encoding="utf-8")
        PostmanAdapter().validate(f)  # must not raise

    def test_missing_info_schema_raises(self, tmp_path: Path) -> None:
        doc = {"info": {"name": "My API"}, "item": []}
        f = tmp_path / "col.json"
        f.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ConverterError):
            PostmanAdapter().validate(f)

    def test_convert_raises_when_npx_missing(self, tmp_path: Path) -> None:
        src = tmp_path / "col.json"
        src.write_text(json.dumps(_POSTMAN_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        with patch(
            "infrastructure.endpoints.converters.postman.shutil.which",
            return_value=None,
        ):
            with pytest.raises(ConverterError, match="Node.js"):
                PostmanAdapter().convert(src, out_dir)

    def test_convert_raises_on_nonzero_returncode(self, tmp_path: Path) -> None:
        src = tmp_path / "col.json"
        src.write_text(json.dumps(_POSTMAN_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "postman error"
        with patch(
            "infrastructure.endpoints.converters.postman.shutil.which",
            return_value="/usr/bin/npx",
        ):
            with patch(
                "infrastructure.endpoints.converters.postman.subprocess.run",
                return_value=mock_result,
            ):
                with pytest.raises(ConverterError, match="postman error"):
                    PostmanAdapter().convert(src, out_dir)

    def test_convert_returns_correct_path_on_success(self, tmp_path: Path) -> None:
        src = tmp_path / "col.json"
        src.write_text(json.dumps(_POSTMAN_DOC), encoding="utf-8")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch(
            "infrastructure.endpoints.converters.postman.shutil.which",
            return_value="/usr/bin/npx",
        ):
            with patch(
                "infrastructure.endpoints.converters.postman.subprocess.run",
                return_value=mock_result,
            ):
                result = PostmanAdapter().convert(src, out_dir)
        assert result == out_dir / "endpoints.json"
