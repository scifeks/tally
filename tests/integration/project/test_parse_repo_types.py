"""Tests for _parse_repo_types helper."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project.wizard import _parse_repo_types  # noqa: E402

pytestmark = pytest.mark.integration


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
