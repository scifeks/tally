"""REPL exit must cancel all in-flight scans."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.locking.cancellation import CancellationToken
from application.repl.interface import REPL
from application.tools.scan_run_registry import get_scan_run_registry


@pytest.fixture(autouse=True)
def _clean_registry():
    registry = get_scan_run_registry()
    yield
    registry.reset()


def test_exit_cancels_all_active_scans(tmp_path) -> None:
    """All in-flight scans are canceled when the REPL exits."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "global.json").write_text("{}")

    registry = get_scan_run_registry()
    tokens = []
    for run_id, project_id in [(1, 10), (2, 20), (3, 10)]:
        t = CancellationToken()
        registry.register(
            run_id=run_id,
            project_id=project_id,
            cancel_token=t,
        )
        tokens.append(t)

    repl = REPL(
        base_path=str(tmp_path),
        runtime_service=MagicMock(),
        project_registry=MagicMock(),
        web_ui_runner=MagicMock(),
        tool_registry=MagicMock(),
    )

    with (
        patch("application.repl.interface.PromptSession") as mock_ps,
        patch("application.repl.interface.print_installed_system_tools"),
        patch("application.repl.interface.print_discovery_summary"),
    ):
        mock_ps.return_value.prompt.side_effect = EOFError
        repl.run()

    for t in tokens:
        assert t.is_set()
