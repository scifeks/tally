"""Unit tests for the DalFox mode wizard prompt logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from application.project.wizard import _interview_dalfox_mode

# ---------------------------------------------------------------------------
# Gate: no base URLs → returns default without prompting
# ---------------------------------------------------------------------------


class TestDalFoxWizardGate:
    def test_no_base_urls_skips_prompt_and_returns_noir(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(base_urls=[], oas3_path="")
        mock_input.assert_not_called()
        assert result == "noir"

    def test_no_base_urls_with_current_mode_returns_current(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(
                base_urls=[], oas3_path="", current_mode="provided"
            )
        mock_input.assert_not_called()
        assert result == "provided"

    def test_no_base_urls_with_oas3_path_still_skips_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(base_urls=[], oas3_path="/some/path.json")
        mock_input.assert_not_called()
        assert result == "noir"


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
        # current_mode="provided" should be used as default when oas3_path is set
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                current_mode="provided",
            )
        assert result == "provided"

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
    def test_noir_accepted_without_oas3_path(self) -> None:
        with patch("builtins.input", return_value="noir"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"

    def test_provided_accepted_when_oas3_path_set(self) -> None:
        with patch("builtins.input", return_value="provided"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/some/endpoints.json",
            )
        assert result == "provided"

    def test_case_insensitive_input(self) -> None:
        with patch("builtins.input", return_value="NOIR"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"


# ---------------------------------------------------------------------------
# Invalid selections with retry
# ---------------------------------------------------------------------------


class TestDalFoxWizardInvalidSelections:
    def test_invalid_mode_retries_until_valid(self) -> None:
        with patch("builtins.input", side_effect=["badvalue", "noir"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"

    def test_crawl_rejected_and_retries(self) -> None:
        # 'crawl' is not a valid DalFox mode
        with patch("builtins.input", side_effect=["crawl", "noir"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"

    def test_provided_without_oas3_path_re_prompts(self) -> None:
        with patch("builtins.input", side_effect=["provided", "noir"]):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "noir"


# ---------------------------------------------------------------------------
# Node.js app constraints
# ---------------------------------------------------------------------------


class TestDalFoxWizardNodeApp:
    def test_node_app_without_oas3_path_returns_empty_without_prompt(
        self,
    ) -> None:
        # No valid modes for node app with no oas3_path; DalFox is skipped
        with patch("builtins.input") as mock_input:
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                node_app=True,
            )
        mock_input.assert_not_called()
        assert result == ""

    def test_node_app_with_oas3_path_default_is_provided(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "provided"

    def test_node_app_with_oas3_path_can_choose_provided(self) -> None:
        with patch("builtins.input", return_value="provided"):
            result = _interview_dalfox_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "provided"

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

        for mode in ("noir", "provided", ""):
            repo = Repository.model_construct(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                dalfox_mode=mode,
            )
            assert repo.dalfox_mode == mode

    def test_default_is_noir(self) -> None:
        from core.config.schemas import Repository

        repo = Repository.model_construct(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
        )
        assert repo.dalfox_mode == "noir"

    def test_crawl_is_invalid_mode(self) -> None:
        from pydantic import ValidationError

        from core.config.schemas import Repository

        with pytest.raises(ValidationError, match="dalfox_mode"):
            Repository(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                dalfox_mode="crawl",
            )

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
