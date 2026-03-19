"""Integration tests for the triage pipeline (no Claude invocation).

These tests exercise the full pipeline end-to-end — real repositories, real
batch creation, real claiming, real finding updates — with only Claude's
subprocess call replaced by a synthetic handler.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.triage.runner import TriageResult, TriageRunner  # noqa: E402
from core.store import make_store  # noqa: E402
from core.store.connection import ConnectionFactory  # noqa: E402
from core.store.repositories.findings import FindingRepository  # noqa: E402
from core.store.repositories.runs import RunRepository  # noqa: E402
from tally_mcp.tools import findings  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_FINDING = {
    "tool": "semgrep",
    "domain": "sast",
    "segment": "sast",
    "repo": "testrepo",
    "finding_type": "vulnerability",
    "severity": "high",
    "confidence": "potential",
    "file_path": "src/app.py",
    "rule_id": "python.sqli",
    "description": "SQL injection",
}

_VALID_UPDATE = {
    "confidence": "confirmed",
    "finding_type": "vulnerability",
    "severity": "high",
    "reasoning": "test",
    "remediation": "fix it",
}


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    n: int = 1,
    overrides: dict | None = None,
) -> int:
    run_id = run_repo.create_run({})
    batch = [
        {**_BASE_FINDING, "file_path": f"src/file{i}.py", **(overrides or {})}
        for i in range(n)
    ]
    finding_repo.upsert_findings(run_id, batch)
    return run_id


def _all_finding_ids(factory: ConnectionFactory) -> list[int]:
    with factory.connect() as conn:
        rows = conn.execute("SELECT id FROM findings ORDER BY id").fetchall()
    return [r["id"] for r in rows]


def _make_mock_semgrep() -> MagicMock:
    t = MagicMock()
    t.name = "semgrep"
    t.skip = False
    t.scan_segment = "sast"
    return t


def _make_synthetic_handler() -> Callable[[int, Callable[..., str], list[int]], str]:
    """Handler that updates every finding in the batch via real MCP tools."""

    def handler(
        batch_id: int,
        render_fn: Callable[..., str],
        finding_ids: list[int],
    ) -> str:
        fdata = asyncio.run(findings.get_findings_batch(finding_ids))
        updates = [{"finding_id": f["id"], **_VALID_UPDATE} for f in fdata]
        asyncio.run(findings.update_findings_batch(updates))
        return "success"

    return handler


def _make_runner_real(
    tmp_path: Path, project: str = "testproject"
) -> tuple[TriageRunner, ConnectionFactory, RunRepository, FindingRepository]:
    """Return a TriageRunner backed by real repositories."""
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()

    run_repo, finding_repo, triage_repo, audit_repo = make_store(tmp_path, project)
    factory = ConnectionFactory(
        tmp_path / "projects" / project / "sqlite" / "findings.db"
    )

    from tally_mcp.context import FindingsContext

    findings.init(
        FindingsContext(
            finding_repo=finding_repo,
            audit_repo=audit_repo,
            triage_repo=triage_repo,
            project_name="",
        )
    )

    runner = TriageRunner(project, run_repo, triage_repo, audit_repo, tmp_path)
    return runner, factory, run_repo, finding_repo


# ---------------------------------------------------------------------------
# Group 1 — .mcp.json structure
# ---------------------------------------------------------------------------


def test_mcp_json_server_type_is_stdio(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)
    mcp_path = runner._write_mcp_config()
    import json

    payload = json.loads(mcp_path.read_text())
    assert payload["mcpServers"]["tally-mcp"]["type"] == "stdio"


def test_mcp_json_command_is_venv_python(tmp_path: Path) -> None:
    runner, _, _, _ = _make_runner_real(tmp_path)
    mcp_path = runner._write_mcp_config()
    import json

    payload = json.loads(mcp_path.read_text())
    expected = str(tmp_path / ".venv" / "bin" / "python")
    assert payload["mcpServers"]["tally-mcp"]["command"] == expected


def test_mcp_json_args_contain_project(tmp_path: Path) -> None:
    runner, _, _, _ = _make_runner_real(tmp_path, project="myproject")
    mcp_path = runner._write_mcp_config()
    import json

    payload = json.loads(mcp_path.read_text())
    args = payload["mcpServers"]["tally-mcp"]["args"]
    assert "--project" in args
    assert "myproject" in args


def test_mcp_json_only_triage_tools_allowed(tmp_path: Path) -> None:
    runner, _, _, _ = _make_runner_real(tmp_path)
    mcp_path = runner._write_mcp_config()
    import json

    payload = json.loads(mcp_path.read_text())
    allow = payload["mcpServers"]["tally-mcp"]["permissions"]["allow"]
    assert allow == ["get_findings_batch", "update_findings_batch"]


def test_mcp_json_deny_star(tmp_path: Path) -> None:
    runner, _, _, _ = _make_runner_real(tmp_path)
    mcp_path = runner._write_mcp_config()
    import json

    payload = json.loads(mcp_path.read_text())
    deny = payload["mcpServers"]["tally-mcp"]["permissions"]["deny"]
    assert deny == ["*"]


# ---------------------------------------------------------------------------
# Group 2 — _run_session() subprocess contract
# ---------------------------------------------------------------------------


def _make_runner_mock(
    tmp_path: Path, project: str = "proj"
) -> tuple[TriageRunner, MagicMock]:
    """Return a TriageRunner with a mock store (all 3 repos unified)."""
    venv_python = tmp_path / ".venv" / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.touch()

    store = MagicMock()
    store.create_run.return_value = 1
    store.reset_stale_batches.return_value = 0
    store.get_active_finding_combos.return_value = []
    store.count_events_since.return_value = 0
    runner = TriageRunner(project, store, store, store, tmp_path)
    return runner, store


def _render_stub(finding_ids: list[int], project: str) -> str:
    return f"stub prompt for finding {finding_ids[0] if finding_ids else 'none'}"


def test_run_session_invokes_claude_binary(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [1])

    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "claude"


def test_run_session_print_flag_present(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [1])

    cmd = mock_run.call_args[0][0]
    assert "--print" in cmd


def test_run_session_skip_permissions_flag(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [1])

    cmd = mock_run.call_args[0][0]
    assert "--dangerously-skip-permissions" in cmd


def test_run_session_disallowed_tools_value(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [1])

    cmd = mock_run.call_args[0][0]
    idx = cmd.index("--disallowedTools")
    assert cmd[idx + 1] == "Bash,Write,Edit,MultiEdit,WebFetch,WebSearch"


def test_run_session_cwd_is_app_root(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [1])

    call_kwargs = mock_run.call_args[1]
    assert call_kwargs["cwd"] == str(tmp_path)


def test_run_session_stdin_contains_finding_id(tmp_path: Path) -> None:
    runner, store = _make_runner_mock(tmp_path)
    store.count_events_since.return_value = 1

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        runner._run_session(_render_stub, [42])

    call_kwargs = mock_run.call_args[1]
    assert "42" in call_kwargs["input"]


# ---------------------------------------------------------------------------
# Group 3 — End-to-end pipeline with real store + synthetic handler
# ---------------------------------------------------------------------------


def test_pipeline_batch_creates_pending_batches(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)

    mock_semgrep = _make_mock_semgrep()
    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.batch()

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM triage_batches WHERE status = 'pending'"
        ).fetchall()
    assert len(rows) >= 1


def test_pipeline_all_batches_completed_after_loop(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id, _ = runner.batch()
        runner._run_batch_loop(run_id, handler)

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM triage_batches WHERE status IN ('pending', 'in_progress')"
        ).fetchall()
    assert len(rows) == 0


def test_pipeline_finding_marked_enriched(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id, _ = runner.batch()
        runner._run_batch_loop(run_id, handler)

    fid = _all_finding_ids(factory)[0]
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT enriched, triaged_at, triaged_by FROM findings WHERE id = ?",
            (fid,),
        ).fetchone()
    assert row["enriched"] == 1
    assert row["triaged_at"] is not None
    assert row["triaged_by"] == "claude-code"


def test_pipeline_audit_log_written(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id, _ = runner.batch()
        runner._run_batch_loop(run_id, handler)

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tool_audit_log WHERE tool_name = 'update_finding'"
        ).fetchall()
    assert len(rows) >= 1


def test_pipeline_result_counts_match(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id, _ = runner.batch()
        result = runner._run_batch_loop(run_id, handler)

    assert isinstance(result, TriageResult)
    assert result.sessions_run == 1
    assert result.success == 1


# ---------------------------------------------------------------------------
# Group 4 — Multi-batch regression (double-claiming fix)
# ---------------------------------------------------------------------------


def test_all_batches_processed_no_stuck_in_progress(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    # Seed 2 findings in different files so batching produces 2+ batches
    seed_run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/alpha.py"},
            {**_BASE_FINDING, "file_path": "src/beta.py", "rule_id": "python.xss"},
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id2, _ = runner.batch()
        runner._run_batch_loop(run_id2, handler)

    with factory.connect() as conn:
        stuck = conn.execute(
            "SELECT * FROM triage_batches WHERE status IN ('pending', 'in_progress')"
        ).fetchall()
    assert len(stuck) == 0


def test_claim_count_equals_batch_count_plus_one(tmp_path: Path) -> None:
    """claim_batch is called exactly N+1 times (N batches + None sentinel)."""
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    # Two findings → should produce at least 1 batch
    seed_run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/a.py"},
            {**_BASE_FINDING, "file_path": "src/b.py", "rule_id": "python.xss"},
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    original_claim = runner._triage_repo.claim_batch
    claim_calls: list[object] = []

    def spy_claim(run_id: int) -> dict | None:
        result = original_claim(run_id)
        claim_calls.append(result)
        return result

    runner._triage_repo.claim_batch = spy_claim  # type: ignore[method-assign]

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id2, total_batches = runner.batch()
        runner._run_batch_loop(run_id2, handler)

    # N batches + 1 None sentinel
    assert len(claim_calls) == total_batches + 1
    assert claim_calls[-1] is None


def test_both_findings_enriched(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    seed_run_id = run_repo.create_run({})
    finding_repo.upsert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/a.py"},
            {**_BASE_FINDING, "file_path": "src/b.py", "rule_id": "python.xss"},
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    with patch("application.triage.runner.tool_registry") as mock_reg:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id2, _ = runner.batch()
        runner._run_batch_loop(run_id2, handler)

    with factory.connect() as conn:
        rows = conn.execute("SELECT enriched, triaged_by FROM findings").fetchall()
    assert all(r["enriched"] == 1 for r in rows)
    assert all(r["triaged_by"] == "claude-code" for r in rows)
