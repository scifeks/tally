"""Unit tests for the DalFox mode wizard prompt logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from application.project.wizard import _interview_dalfox_mode

# ---------------------------------------------------------------------------
# Gate: no base URLs → returns crawl without prompting
# ---------------------------------------------------------------------------


class TestDalFoxWizardGate:
    def test_no_base_urls_returns_crawl_without_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(base_urls=[], oas3_path="")
        mock_input.assert_not_called()
        assert result == "crawl"

    def test_no_base_urls_with_oas3_path_still_returns_crawl(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(base_urls=[], oas3_path="/some/path.json")
        mock_input.assert_not_called()
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Default selection
# ---------------------------------------------------------------------------


class TestDalFoxWizardDefault:
    def test_no_oas3_path_default_is_noir(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"

    def test_with_oas3_path_default_is_provided(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
            )
        assert result == "provided"

    def test_current_mode_overrides_default_when_valid(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="crawl",
            )
        assert result == "crawl"

    def test_invalid_current_mode_falls_back_to_computed_default(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="unknown_value",
            )
        assert result == "noir"


# ---------------------------------------------------------------------------
# Valid selections
# ---------------------------------------------------------------------------


class TestDalFoxWizardValidSelections:
    @pytest.mark.parametrize("choice", ["crawl", "noir"])
    def test_valid_non_provided_modes_accepted(self, choice: str) -> None:
        with patch("builtins.input", return_value=choice):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == choice

    def test_provided_accepted_when_oas3_path_set(self) -> None:
        with patch("builtins.input", return_value="provided"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/some/endpoints.json",
            )
        assert result == "provided"

    def test_case_insensitive_input(self) -> None:
        with patch("builtins.input", return_value="CRAWL"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Invalid selections with retry
# ---------------------------------------------------------------------------


class TestDalFoxWizardInvalidSelections:
    def test_invalid_mode_retries_until_valid(self) -> None:
        with patch("builtins.input", side_effect=["badvalue", "crawl"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"

    def test_provided_without_oas3_path_re_prompts(self) -> None:
        with patch("builtins.input", side_effect=["provided", "crawl"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Node.js app constraints
# ---------------------------------------------------------------------------


class TestDalFoxWizardNodeApp:
    def test_node_app_without_oas3_path_returns_crawl_without_prompt(
        self,
    ) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                node_app=True,
            )
        mock_input.assert_not_called()
        assert result == "crawl"

    def test_node_app_with_oas3_path_default_is_provided(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "provided"

    def test_node_app_with_oas3_path_can_choose_crawl(self) -> None:
        with patch("builtins.input", return_value="crawl"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "crawl"

    def test_noir_rejected_when_node_app_with_oas3_path(self) -> None:
        with patch("builtins.input", side_effect=["noir", "provided"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "provided"

    def test_current_mode_noir_overridden_when_node_app(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
                current_mode="noir",
            )
        assert result == "provided"


# ---------------------------------------------------------------------------
# Repository.dalfox_mode field validation
# ---------------------------------------------------------------------------


class TestRepositoryDalFoxMode:
    def test_valid_modes_accepted(self) -> None:
        from core.config.schemas import Repository

        for mode in ("crawl", "noir", "provided", ""):
            repo = Repository.model_construct(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                dalfox_mode=mode,
            )
            assert repo.dalfox_mode == mode

    def test_default_is_crawl(self) -> None:
        from core.config.schemas import Repository

        repo = Repository.model_construct(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
        )
        assert repo.dalfox_mode == "crawl"

    def test_invalid_mode_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        from core.config.schemas import Repository

        with pytest.raises(ValidationError, match="dalfox_mode"):
            Repository(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                dalfox_mode="bad_mode",
            )

    def test_node_app_with_noir_mode_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        from core.config.schemas import Repository

        with pytest.raises(ValidationError, match="noir"):
            Repository(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                node_app=True,
                dalfox_mode="noir",
            )
