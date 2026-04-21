"""Tests for _validate_repo_types helper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project.wizard import _validate_repo_types  # noqa: E402

pytestmark = pytest.mark.integration


class TestValidateRepoTypes:
    def test_valid_api(self) -> None:
        assert _validate_repo_types(["api"]) is None

    def test_valid_ui(self) -> None:
        assert _validate_repo_types(["ui-old"]) is None

    def test_valid_library(self) -> None:
        assert _validate_repo_types(["library"]) is None

    def test_valid_api_ui(self) -> None:
        assert _validate_repo_types(["api", "ui-old"]) is None

    def test_valid_ui_api(self) -> None:
        assert _validate_repo_types(["ui-old", "api"]) is None

    def test_empty_returns_error(self) -> None:
        result = _validate_repo_types([])
        assert result is not None
        assert "required" in result.lower()

    def test_invalid_type_returns_error(self) -> None:
        result = _validate_repo_types(["backend"])
        assert result is not None
        assert "backend" in result

    def test_library_with_api_returns_error(self) -> None:
        result = _validate_repo_types(["library", "api"])
        assert result is not None
        assert "library" in result.lower()
        assert "exclusive" in result.lower() or "cannot" in result.lower()

    def test_library_with_ui_returns_error(self) -> None:
        result = _validate_repo_types(["library", "ui-old"])
        assert result is not None
        assert "library" in result.lower()

    def test_library_with_api_and_ui_returns_error(self) -> None:
        result = _validate_repo_types(["library", "api", "ui-old"])
        assert result is not None
