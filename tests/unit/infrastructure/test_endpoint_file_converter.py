"""Unit tests for the EndpointFileConverter adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.endpoints.converters.base import ConverterError
from infrastructure.endpoints.converters.endpoint_file_converter import (
    EndpointFileConverter,
)


class TestEndpointFileConverter:
    def test_returns_parsed_oas3_dict_for_valid_oas3_file(self, tmp_path: Path) -> None:
        src = tmp_path / "api.json"
        src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}'
        )
        result = EndpointFileConverter().to_oas3(src)
        assert isinstance(result, dict)
        assert result.get("openapi", "").startswith("3.")

    def test_propagates_converter_error_for_missing_source(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "missing.json"
        with pytest.raises(ConverterError):
            EndpointFileConverter().to_oas3(src)

    def test_temp_artifacts_do_not_persist(self, tmp_path: Path) -> None:
        src = tmp_path / "api.json"
        src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}'
        )
        EndpointFileConverter().to_oas3(src)
        assert list(tmp_path.iterdir()) == [src]
