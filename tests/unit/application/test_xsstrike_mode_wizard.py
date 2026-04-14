"""Unit tests for the XSStrike mode wizard prompt logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from application.project.wizard import _interview_xsstrike_mode

# ---------------------------------------------------------------------------
# Gate: no base URLs → returns default without prompting
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardGate:
    def test_no_base_urls_returns_noir_katana_without_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(base_urls=[], oas3_path="")
        mock_input.assert_not_called()
        assert result == "noir+katana"

    def test_no_base_urls_with_oas3_path_still_skips_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(base_urls=[], oas3_path="/some/path.json")
        mock_input.assert_not_called()
        assert result == "noir+katana"

    def test_no_base_urls_with_current_mode_returns_current(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(
                base_urls=[], oas3_path="", current_mode="provided"
            )
        mock_input.assert_not_called()
        assert result == "provided"


# ---------------------------------------------------------------------------
# Default selection (Enter key with no input)
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardDefault:
    def test_default_is_noir_katana(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir+katana"

    def test_with_oas3_path_default_is_still_noir_katana(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
            )
        assert result == "noir+katana"

    def test_current_mode_provided_used_as_default_when_oas3_path_set(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                current_mode="provided",
            )
        assert result == "provided"

    def test_legacy_crawl_current_mode_maps_to_auto_as_default(self) -> None:
        # "crawl" is a legacy value that normalises to "auto"
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="crawl",
            )
        assert result == "auto"

    def test_invalid_current_mode_falls_back_to_noir_katana(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="unknown_value",
            )
        assert result == "noir+katana"


# ---------------------------------------------------------------------------
# Valid selections
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardValidSelections:
    @pytest.mark.parametrize("choice", ["auto", "noir+katana"])
    def test_valid_non_provided_modes_accepted(self, choice: str) -> None:
        with patch("builtins.input", return_value=choice):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == choice

    def test_provided_accepted_when_oas3_path_set(self) -> None:
        with patch("builtins.input", return_value="provided"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/some/endpoints.json",
            )
        assert result == "provided"

    def test_legacy_crawl_maps_to_auto(self) -> None:
        with patch("builtins.input", return_value="crawl"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "auto"

    def test_legacy_noir_maps_to_noir_katana(self) -> None:
        with patch("builtins.input", return_value="noir"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir+katana"

    def test_legacy_katana_maps_to_noir_katana(self) -> None:
        with patch("builtins.input", return_value="katana"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir+katana"

    def test_case_insensitive_input(self) -> None:
        with patch("builtins.input", return_value="AUTO"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "auto"


# ---------------------------------------------------------------------------
# Invalid selections with retry
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardInvalidSelections:
    def test_invalid_mode_retries_until_valid(self) -> None:
        with patch("builtins.input", side_effect=["badvalue", "auto"]):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "auto"

    def test_provided_without_oas3_path_re_prompts(self) -> None:
        with patch("builtins.input", side_effect=["provided", "auto"]):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "auto"


# ---------------------------------------------------------------------------
# Repository.xsstrike_mode field validation
# ---------------------------------------------------------------------------


class TestRepositoryXSSTrikeMode:
    def test_valid_modes_accepted(self) -> None:
        from core.config.schemas import Repository

        for mode in ("auto", "noir+katana", "provided", ""):
            repo = Repository.model_construct(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                xsstrike_mode=mode,
            )
            assert repo.xsstrike_mode == mode

    def test_default_is_noir_katana(self) -> None:
        from core.config.schemas import Repository

        repo = Repository.model_construct(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
        )
        assert repo.xsstrike_mode == "noir+katana"

    def test_legacy_crawl_migrates_to_auto(self) -> None:
        from core.config.schemas import Repository

        repo = Repository(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
            xsstrike_mode="crawl",
        )
        assert repo.xsstrike_mode == "auto"

    def test_legacy_noir_migrates_to_noir_katana(self) -> None:
        from core.config.schemas import Repository

        repo = Repository(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
            xsstrike_mode="noir",
        )
        assert repo.xsstrike_mode == "noir+katana"

    def test_legacy_katana_migrates_to_noir_katana(self) -> None:
        from core.config.schemas import Repository

        repo = Repository(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
            xsstrike_mode="katana",
        )
        assert repo.xsstrike_mode == "noir+katana"

    def test_invalid_mode_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        from core.config.schemas import Repository

        with pytest.raises(ValidationError, match="xsstrike_mode"):
            Repository(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                xsstrike_mode="bad_mode",
            )
