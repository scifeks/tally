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
    store.count_audit_events_since.return_value = 0

    runner = TriageRunner(project, store, tmp_path)
    return runner, store


def _render_stub(finding_ids: list[int], project: str) -> str:
    return "stub prompt text"


def _make_mock_tool(name: str, *, skip: bool, scan_segment: str = "sast") -> MagicMock:
    t = MagicMock()
    t.name = name
    t.skip = skip
    t.scan_segment = scan_segment
    return t


def _make_semgrep_batch(batch_id: int, finding_ids: list[int]) -> dict:
    return {
        "id": batch_id,
        "finding_ids": finding_ids,
        "batch_data": [
            {"id": fid, "tool": "semgrep", "file": f"src/file{fid}.py"}
            for fid in finding_ids
        ],
    }


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
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = [mock_nmap]
        runner.batch()

    skip_tools = store.get_active_finding_combos.call_args[0][0]
    assert "nmap" in skip_tools


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
        outcome = runner._run_session(_render_stub, [1, 2])

    assert outcome == "success"


def test_run_session_incomplete_when_no_audit_rows(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.count_audit_events_since.return_value = 0

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        outcome = runner._run_session(_render_stub, [1])

    assert outcome == "incomplete"


def test_run_session_failed_nonzero_exit(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "some error"

    with patch("subprocess.run", return_value=mock_result):
        outcome = runner._run_session(_render_stub, [1])

    assert outcome == "failed"
    store.count_audit_events_since.assert_not_called()


def test_run_session_failed_on_timeout(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    with patch(
        "subprocess.run",
        side_effect=TimeoutExpired(cmd="claude", timeout=300),
    ):
        outcome = runner._run_session(_render_stub, [1])

    assert outcome == "failed"


def test_run_session_failed_on_subprocess_exception(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)

    with patch("subprocess.run", side_effect=OSError("command not found")):
        outcome = runner._run_session(_render_stub, [1])

    assert outcome == "failed"


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


def test_run_calls_batch_then_sessions(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [_make_semgrep_batch(1, [1]), None]
    store.count_audit_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
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
    nmap_batch = {
        "id": 1,
        "finding_ids": [1, 2],
        "batch_data": [
            {"id": 1, "tool": "nmap"},
            {"id": 2, "tool": "nmap"},
        ],
    }
    store.claim_triage_batch.side_effect = [nmap_batch, None]
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_nmap
        result = runner.run()

    assert result.sessions_run == 0
    store.complete_triage_batch.assert_called_once_with(1, "success")


def test_run_deletes_mcp_json_on_success(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.return_value = None

    runner.run()

    assert not (tmp_path / ".mcp.json").exists()


def test_run_deletes_mcp_json_on_exception(tmp_path: Path) -> None:
    """finally block cleans up .mcp.json even when a session raises."""
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [_make_semgrep_batch(1, [1]), None]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        with patch.object(runner, "_run_session", side_effect=RuntimeError("crash")):
            with pytest.raises(RuntimeError, match="crash"):
                runner.run()

    assert not (tmp_path / ".mcp.json").exists()


# ---------------------------------------------------------------------------
# run_dry_run()
# ---------------------------------------------------------------------------


def test_run_dry_run_calls_batch(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.return_value = None
    runner.run_dry_run()
    store.create_run.assert_called_once()  # batch() is invoked


def test_run_dry_run_marks_all_batches_success(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [
        _make_semgrep_batch(10, [1, 2]),
        _make_semgrep_batch(11, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run_dry_run()

    assert store.complete_triage_batch.call_count == 2
    store.complete_triage_batch.assert_any_call(10, "success")
    store.complete_triage_batch.assert_any_call(11, "success")


def test_run_dry_run_no_pending_remain(tmp_path: Path) -> None:
    """Every claimed batch is completed — none left pending/in_progress."""
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [
        _make_semgrep_batch(5, [1]),
        _make_semgrep_batch(6, [2]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run_dry_run()

    calls = [c.args for c in store.complete_triage_batch.call_args_list]
    assert all(status == "success" for _, status in calls)


def test_run_dry_run_prompt_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [
        _make_semgrep_batch(7, [42]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        with caplog.at_level(logging.DEBUG, logger="tally_mcp.triage"):
            runner.run_dry_run()

    log_text = " ".join(r.message for r in caplog.records)
    assert "42" in log_text  # finding ID from batch_data appears
    assert "BATCH 7" in log_text  # delimiter present


def test_run_dry_run_does_not_start_mcp(tmp_path: Path) -> None:
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.return_value = None
    with patch.object(runner, "_write_mcp_config") as mock_write:
        runner.run_dry_run()
    mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# _run_batch_loop()
# ---------------------------------------------------------------------------


def _make_nmap_batch(batch_id: int, finding_ids: list[int]) -> dict:
    return {
        "id": batch_id,
        "finding_ids": finding_ids,
        "batch_data": [{"id": fid, "tool": "nmap"} for fid in finding_ids],
    }


def test_run_batch_loop_skip_completes_without_handler(tmp_path: Path) -> None:
    """skip-strategy batches are auto-completed; handler is never called."""
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [_make_nmap_batch(1, [10, 11]), None]
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    handler = MagicMock(return_value="success")
    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_tool.return_value = mock_nmap
        result = runner._run_batch_loop(1, handler)

    handler.assert_not_called()
    store.complete_triage_batch.assert_called_once_with(1, "success")
    assert result.sessions_run == 0
    assert result.success == 0


def test_run_batch_loop_returns_correct_counts(tmp_path: Path) -> None:
    """sessions_run / success / failed / incomplete are tallied correctly."""
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [
        _make_semgrep_batch(1, [1]),
        _make_semgrep_batch(2, [2]),
        _make_semgrep_batch(3, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    outcomes = ["success", "failed", "incomplete"]
    handler = MagicMock(side_effect=outcomes)
    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_tool.return_value = mock_semgrep
        result = runner._run_batch_loop(99, handler)

    assert result.sessions_run == 3
    assert result.success == 1
    assert result.failed == 1
    assert result.incomplete == 1


def test_run_batch_loop_exhausts_all_batches(tmp_path: Path) -> None:
    """Loop exits only when claim_triage_batch returns None."""
    runner, store = _make_runner(tmp_path)
    store.claim_triage_batch.side_effect = [
        _make_semgrep_batch(1, [1]),
        _make_semgrep_batch(2, [2]),
        _make_semgrep_batch(3, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    handler = MagicMock(return_value="success")
    with patch("tally_mcp.triage.tool_registry") as mock_reg:
        mock_reg.get_tool.return_value = mock_semgrep
        runner._run_batch_loop(99, handler)

    assert store.claim_triage_batch.call_count == 4  # 3 batches + None sentinel
    assert handler.call_count == 3
