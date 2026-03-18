"""Unit tests for TriageRunner (tally_mcp.triage)."""

from __future__ import annotations

import sys
from pathlib import Path
from subprocess import TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tally_mcp.triage import TriageResult, TriageRunner  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(
    tmp_path: Path, project: str = "proj"
) -> tuple[TriageRunner, MagicMock]:
    """Return a TriageRunner with a mock SQLiteStore and a stub venv python."""
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()

    store = MagicMock()
    store.create_run.return_value = 1
    store.reset_stale_triage_batches.return_value = 0
    store.get_active_finding_combos.return_value = []
    store.get_untriaged_findings.return_value = []
    store.count_audit_events_since.return_value = 0

    runner = TriageRunner(project, store, tmp_path)
    return runner, store


# ---------------------------------------------------------------------------
# batch()
# ---------------------------------------------------------------------------


def test_batch_resets_stale_before_creating(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = []

    runner.batch()

    store.reset_stale_triage_batches.assert_called_once()
    store.create_triage_batches.assert_not_called()


def test_batch_calls_create_per_combo(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = [
        ("semgrep", "repo1", "sast"),
        ("zap", "repo1", "api"),
    ]
    store.create_triage_batches.return_value = 2

    run_id, total = runner.batch()

    assert store.create_triage_batches.call_count == 2
    assert total == 4  # 2 + 2
    store.create_triage_batches.assert_any_call(run_id, "semgrep", "repo1", "sast")
    store.create_triage_batches.assert_any_call(run_id, "zap", "repo1", "api")


def test_batch_passes_skip_tools_to_store(tmp_path: Path) -> None:
    """get_active_finding_combos receives a frozenset containing skip tools."""
    runner, store = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = []

    runner.batch()

    skip_tools = store.get_active_finding_combos.call_args[0][0]
    assert "nmap" in skip_tools
    assert "tree-sitter" in skip_tools


def test_batch_resets_before_fetching_combos(tmp_path: Path) -> None:
    """reset_stale_triage_batches is called before get_active_finding_combos."""
    runner, store = _make_runner(tmp_path)
    call_order: list[str] = []
    store.reset_stale_triage_batches.side_effect = lambda *a, **k: (
        call_order.append("reset") or 0
    )
    store.get_active_finding_combos.side_effect = lambda *a, **k: (
        call_order.append("combos") or []
    )

    runner.batch()

    assert call_order == ["reset", "combos"]


def test_batch_error_raises_runtime_error(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = [("semgrep", "repo1", "sast")]
    store.create_triage_batches.side_effect = RuntimeError("db locked")

    with pytest.raises(RuntimeError, match="Batching failed"):
        runner.batch()


# ---------------------------------------------------------------------------
# _run_session()
# ---------------------------------------------------------------------------


def test_run_session_success(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.count_audit_events_since.return_value = 3

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        outcome = runner._run_session("code_trace", [1, 2])

    assert outcome == "success"


def test_run_session_incomplete_when_no_audit_rows(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.count_audit_events_since.return_value = 0

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        outcome = runner._run_session("code_trace", [1])

    assert outcome == "incomplete"


def test_run_session_failed_nonzero_exit(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"

    with patch("subprocess.run", return_value=mock_result):
        outcome = runner._run_session("code_trace", [1])

    assert outcome == "failed"
    store.count_audit_events_since.assert_not_called()


def test_run_session_failed_on_timeout(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    with patch(
        "subprocess.run",
        side_effect=TimeoutExpired(cmd="claude", timeout=300),
    ):
        outcome = runner._run_session("code_trace", [1])

    assert outcome == "failed"


def test_run_session_failed_on_subprocess_exception(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    with patch("subprocess.run", side_effect=OSError("command not found")):
        outcome = runner._run_session("code_trace", [1])

    assert outcome == "failed"


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_calls_batch_then_sessions(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_untriaged_findings.return_value = [(1, "semgrep")]
    store.count_audit_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = runner.run()

    store.create_run.assert_called_once()  # from batch()
    assert isinstance(result, TriageResult)
    assert result.sessions_run == 1
    assert result.success == 1
    assert result.failed == 0
    assert result.incomplete == 0


def test_run_skips_skip_strategy_tools(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_untriaged_findings.return_value = [
        (1, "nmap"),
        (2, "tree-sitter"),
    ]

    result = runner.run()

    assert result.sessions_run == 0


def test_run_deletes_mcp_json_on_success(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.get_untriaged_findings.return_value = []

    runner.run()

    assert not (tmp_path / ".mcp.json").exists()


def test_run_deletes_mcp_json_on_exception(tmp_path: Path) -> None:
    """finally block cleans up .mcp.json even when a session raises."""
    runner, store = _make_runner(tmp_path)
    store.get_untriaged_findings.return_value = [(1, "semgrep")]

    with patch.object(runner, "_run_session", side_effect=RuntimeError("crash")):
        with pytest.raises(RuntimeError, match="crash"):
            runner.run()

    assert not (tmp_path / ".mcp.json").exists()
