"""Tests for why execute_tool_passes did not run a tool."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.tools.scan_types.execution import execute_tool_passes
from application.tools.scan_types.models import ScanTypeConfig
from domain.pipeline.scan_events import SKIP_DECLINED, SKIP_NOT_APPLICABLE
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import TransportType


def _config(confirm: bool) -> ScanTypeConfig:
    prompt = MagicMock()
    prompt.confirm.return_value = confirm
    return ScanTypeConfig(
        project_name="proj",
        base_path="/tmp/proj",
        tool_config=ToolExecutionConfig(noir_provider=None),
        run_id=1,
        prompt=prompt,
    )


def _tool(transport: TransportType, passes: list) -> MagicMock:
    tool = MagicMock()
    tool.name = "mytool"
    tool.transport = transport
    tool.build_execution_passes.return_value = passes
    return tool


class TestExecuteToolPassesSkipKind:
    @pytest.mark.parametrize(
        ("tool", "confirm", "expected"),
        [
            pytest.param(
                _tool(TransportType.CLI, [MagicMock()]),
                False,
                SKIP_DECLINED,
                id="prompt-declined",
            ),
            pytest.param(
                _tool(TransportType.CLI, []),
                True,
                SKIP_NOT_APPLICABLE,
                id="no-passes",
            ),
            pytest.param(
                _tool(TransportType.HTTP, [MagicMock()]),
                True,
                SKIP_NOT_APPLICABLE,
                id="http-transport",
            ),
        ],
    )
    def test_returns_the_skip_kind(
        self, tool: MagicMock, confirm: bool, expected: str
    ) -> None:
        outcome = execute_tool_passes(tool, MagicMock(), _config(confirm), MagicMock())
        assert outcome == expected
