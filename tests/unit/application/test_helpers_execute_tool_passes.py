"""Unit tests for _execute_tool_passes in application/tools/scan_types/_helpers.py."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from application.tools.scan_types._helpers import _execute_tool_passes
from domain.tools.scan_types.models import ScanTypeConfig


def _make_config(**overrides) -> ScanTypeConfig:
    defaults: dict = dict(
        project_name="proj",
        base_path="/tmp/proj",
        config_manager=MagicMock(),
        run_id=1,
    )
    defaults.update(overrides)
    return ScanTypeConfig(**defaults)


def _make_tool(name: str = "mytool") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.build_execution_passes.return_value = [MagicMock()]
    tool.merge_pass_results.return_value = MagicMock()
    return tool


class TestExecuteToolPassesApproval:
    def test_auto_approve_skips_all_prompts(self) -> None:
        """When config.auto_approve is True, no input() calls are made."""
        config = _make_config(auto_approve=True)
        tool = _make_tool()
        executor = MagicMock()

        with patch("builtins.input") as mock_input:
            result = _execute_tool_passes(tool, MagicMock(), config, executor)

        mock_input.assert_not_called()
        assert result is not None

    def test_user_declines_run_prompt_returns_none(self) -> None:
        """When user answers 'n' to 'Run X?', returns None."""
        config = _make_config()
        tool = _make_tool()

        with patch("builtins.input", return_value="n"):
            result = _execute_tool_passes(
                tool, MagicMock(), config, executor=MagicMock()
            )

        assert result is None
        assert config.auto_approve is False

    def test_user_approves_no_remaining_tools_no_approve_all_prompt(self) -> None:
        """With remaining_tools=0, 'Approve all remaining?' is never shown."""
        config = _make_config()
        tool = _make_tool()
        executor = MagicMock()

        with patch("builtins.input", return_value="y") as mock_input:
            result = _execute_tool_passes(
                tool, MagicMock(), config, executor, remaining_tools=0
            )

        # Only the "Run X?" prompt should have been asked — not "Approve all remaining?"
        mock_input.assert_called_once_with(f"Run {tool.name}? [y/N]: ")
        assert result is not None
        assert config.auto_approve is False

    def test_user_approves_with_remaining_shows_approve_all_prompt(self) -> None:
        """With remaining_tools=2, 'Approve all remaining?' IS shown."""
        config = _make_config()
        tool = _make_tool()
        executor = MagicMock()

        with patch("builtins.input", side_effect=["y", "n"]) as mock_input:
            result = _execute_tool_passes(
                tool, MagicMock(), config, executor, remaining_tools=2
            )

        assert mock_input.call_count == 2
        assert mock_input.call_args_list[1] == call("Approve all remaining? [y/N]: ")
        assert result is not None
        assert config.auto_approve is False  # user answered 'n' to approve-all

    def test_approve_all_sets_auto_approve(self) -> None:
        """Answering 'y' to 'Approve all remaining?' sets config.auto_approve=True."""
        config = _make_config()
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "y"]):
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=1
            )

        assert config.auto_approve is True

    def test_approve_all_fires_on_auto_approve_callback(self) -> None:
        """When auto_approve is set, on_auto_approve callback is invoked."""
        callback = MagicMock()
        config = _make_config(on_auto_approve=callback)
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "y"]):
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=1
            )

        callback.assert_called_once_with()

    def test_decline_approve_all_does_not_fire_callback(self) -> None:
        """Declining 'Approve all remaining?' does not invoke the callback."""
        callback = MagicMock()
        config = _make_config(on_auto_approve=callback)
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "n"]):
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=1
            )

        callback.assert_not_called()
        assert config.auto_approve is False

    def test_no_callback_set_does_not_raise(self) -> None:
        """When on_auto_approve is None, approving all does not raise."""
        config = _make_config(on_auto_approve=None)
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "y"]):
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=1
            )

        assert config.auto_approve is True

    def test_eof_on_run_prompt_returns_none(self) -> None:
        """EOFError on the 'Run X?' prompt returns None gracefully."""
        config = _make_config()
        tool = _make_tool()

        with patch("builtins.input", side_effect=EOFError):
            result = _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=2
            )

        assert result is None
        assert config.auto_approve is False

    def test_eof_on_approve_all_prompt_does_not_raise(self) -> None:
        """EOFError on the 'Approve all remaining?' prompt is handled gracefully."""
        config = _make_config()
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", EOFError()]):
            result = _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=1
            )

        assert result is not None
        assert config.auto_approve is False


class TestExecuteToolPassesOrchestratorIntegration:
    def test_callback_propagates_to_orchestrator_auto_approve(self) -> None:
        """Simulates orchestrator pattern: callback updates external state."""
        shared_state: dict[str, bool] = {"auto_approve": False}

        def _on_approve() -> None:
            shared_state["auto_approve"] = True

        config = _make_config(on_auto_approve=_on_approve)
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "y"]):
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=3
            )

        assert shared_state["auto_approve"] is True

    @pytest.mark.parametrize("remaining", [1, 2, 10])
    def test_approve_all_shown_for_any_positive_remaining(self, remaining: int) -> None:
        """'Approve all remaining?' appears for any remaining_tools > 0."""
        config = _make_config()
        tool = _make_tool()

        with patch("builtins.input", side_effect=["y", "n"]) as mock_input:
            _execute_tool_passes(
                tool, MagicMock(), config, MagicMock(), remaining_tools=remaining
            )

        assert mock_input.call_count == 2
