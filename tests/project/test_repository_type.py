"""Tests for repository type validation in schemas and manager helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas import Repository  # noqa: E402
from core.project.manager import (  # noqa: E402
    _parse_repo_types,
    _validate_repo_types,
)

# ---------------------------------------------------------------------------
# _parse_repo_types
# ---------------------------------------------------------------------------


class TestParseRepoTypes:
    def test_single_type(self) -> None:
        assert _parse_repo_types("api") == ["api"]

    def test_multiple_types(self) -> None:
        assert _parse_repo_types("api,ui") == ["api", "ui"]

    def test_strips_spaces(self) -> None:
        assert _parse_repo_types("api, ui") == ["api", "ui"]

    def test_leading_trailing_spaces(self) -> None:
        assert _parse_repo_types(" ui ") == ["ui"]

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_repo_types("") == []

    def test_only_commas_returns_empty(self) -> None:
        assert _parse_repo_types(",,,") == []

    def test_library_single(self) -> None:
        assert _parse_repo_types("library") == ["library"]


# ---------------------------------------------------------------------------
# _validate_repo_types
# ---------------------------------------------------------------------------


class TestValidateRepoTypes:
    def test_valid_api(self) -> None:
        assert _validate_repo_types(["api"]) is None

    def test_valid_ui(self) -> None:
        assert _validate_repo_types(["ui"]) is None

    def test_valid_library(self) -> None:
        assert _validate_repo_types(["library"]) is None

    def test_valid_api_ui(self) -> None:
        assert _validate_repo_types(["api", "ui"]) is None

    def test_valid_ui_api(self) -> None:
        assert _validate_repo_types(["ui", "api"]) is None

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
        result = _validate_repo_types(["library", "ui"])
        assert result is not None
        assert "library" in result.lower()

    def test_library_with_api_and_ui_returns_error(self) -> None:
        result = _validate_repo_types(["library", "api", "ui"])
        assert result is not None


# ---------------------------------------------------------------------------
# Repository schema validation
# ---------------------------------------------------------------------------


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "type": ["api"],
        "path": str(_TALLY_ROOT),
        "languages": ["python"],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


class TestRepositoryTypeSchema:
    def test_valid_api(self) -> None:
        repo = _make_repo(type=["api"])
        assert repo.type == ["api"]

    def test_valid_ui(self) -> None:
        repo = _make_repo(type=["ui"])
        assert repo.type == ["ui"]

    def test_valid_library(self) -> None:
        repo = _make_repo(type=["library"])
        assert repo.type == ["library"]

    def test_valid_api_ui(self) -> None:
        repo = _make_repo(type=["api", "ui"])
        assert repo.type == ["api", "ui"]

    def test_missing_type_raises(self) -> None:
        with pytest.raises(Exception):
            Repository(  # type: ignore[call-arg]
                name="r",
                path=str(_TALLY_ROOT),
                languages=[],
            )

    def test_empty_type_raises(self) -> None:
        with pytest.raises(Exception):
            _make_repo(type=[])

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid"):
            _make_repo(type=["backend"])

    def test_library_with_api_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "api"])

    def test_library_with_ui_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "ui"])
