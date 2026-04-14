"""Unit tests for the XSStrike mode wizard prompt logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from application.project.wizard import _interview_xsstrike_mode

# ---------------------------------------------------------------------------
# Gate: no base URLs → returns default without prompting
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardGate:
    def test_no_base_urls_returns_auto_without_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(base_urls=[], oas3_path="")
        mock_input.assert_not_called()
        assert result == "auto"

    def test_no_base_urls_with_oas3_path_still_skips_prompt(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(base_urls=[], oas3_path="/some/path.json")
        mock_input.assert_not_called()
        assert result == "auto"

    def test_no_base_urls_with_current_mode_returns_current(self) -> None:
        with patch("builtins.input") as mock_input:
            result = _interview_xsstrike_mode(
                base_urls=[], oas3_path="", current_mode="crawl"
            )
        mock_input.assert_not_called()
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Default selection
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardDefault:
    def test_no_oas3_path_default_is_auto(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "auto"

    def test_with_oas3_path_default_is_auto(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
            )
        assert result == "auto"

    def test_current_mode_overrides_default_when_valid(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="crawl",
            )
        assert result == "crawl"

    def test_invalid_current_mode_falls_back_to_auto(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                current_mode="unknown_value",
            )
        assert result == "auto"


# ---------------------------------------------------------------------------
# Valid selections
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardValidSelections:
    @pytest.mark.parametrize("choice", ["auto", "crawl", "katana", "noir"])
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

    def test_case_insensitive_input(self) -> None:
        with patch("builtins.input", return_value="CRAWL"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Invalid selections with retry
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardInvalidSelections:
    def test_invalid_mode_retries_until_valid(self) -> None:
        with patch("builtins.input", side_effect=["badvalue", "crawl"]):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"

    def test_provided_without_oas3_path_re_prompts(self) -> None:
        with patch("builtins.input", side_effect=["provided", "crawl"]):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"], oas3_path=""
            )
        assert result == "crawl"


# ---------------------------------------------------------------------------
# Node.js app constraints
# ---------------------------------------------------------------------------


class TestXSSTrikeWizardNodeApp:
    def test_node_app_without_oas3_path_default_is_auto(self) -> None:
        # katana, auto, crawl are valid for node_app; auto is the default
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                node_app=True,
            )
        assert result == "auto"

    def test_node_app_can_choose_katana(self) -> None:
        with patch("builtins.input", return_value="katana"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                node_app=True,
            )
        assert result == "katana"

    def test_node_app_with_oas3_path_default_is_auto(self) -> None:
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "auto"

    def test_node_app_with_oas3_path_can_choose_crawl(self) -> None:
        with patch("builtins.input", return_value="crawl"):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
            )
        assert result == "crawl"

    def test_noir_rejected_when_node_app(self) -> None:
        with patch("builtins.input", side_effect=["noir", "auto"]):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="",
                node_app=True,
            )
        assert result == "auto"

    def test_current_mode_noir_overridden_when_node_app(self) -> None:
        # noir not valid for node_app → effective_default falls back to "auto"
        with patch("builtins.input", return_value=""):
            result = _interview_xsstrike_mode(
                base_urls=["http://localhost:8080"],
                oas3_path="/endpoints.json",
                node_app=True,
                current_mode="noir",
            )
        assert result == "auto"


# ---------------------------------------------------------------------------
# Repository.xsstrike_mode field validation
# ---------------------------------------------------------------------------


class TestRepositoryXSSTrikeMode:
    def test_valid_modes_accepted(self) -> None:
        from core.config.schemas import Repository

        for mode in ("auto", "crawl", "katana", "noir", "provided", ""):
            repo = Repository.model_construct(
                name="r",
                type=["api"],
                path="/tmp",
                languages=[],
                xsstrike_mode=mode,
            )
            assert repo.xsstrike_mode == mode

    def test_default_is_crawl(self) -> None:
        from core.config.schemas import Repository

        repo = Repository.model_construct(
            name="r",
            type=["api"],
            path="/tmp",
            languages=[],
        )
        assert repo.xsstrike_mode == "crawl"

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
                xsstrike_mode="noir",
            )
