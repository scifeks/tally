"""Integration tests for the triage pipeline (no Claude invocation).

These tests exercise the full pipeline end-to-end against real
repositories, real batch creation, real claiming, and real finding
updates, with the triage backend port replaced by a stub. The argv
contract for the real Claude adapter is covered separately under
``tests/integration/agents/``.
"""
# ruff: noqa: E402, I001

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.locking.cancellation import CancellationToken  # noqa: E402
from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
    TriageBackendPort,
    TriageSessionResult,
)
from application.triage.runner import (  # noqa: E402
    TriageCancelled,
    TriageResult,
    TriageRunner,
)
from domain.triage.entry import TriageBatchRow  # noqa: E402
from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent  # noqa: E402
from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402
from tally_mcp.context import FindingsContext  # noqa: E402
from tally_mcp.tools import findings  # noqa: E402

pytestmark = pytest.mark.integration

# Helpers

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


class _StubTriageAgent(TriageBackendPort):
    """Returns a successful TriageSessionResult on every call."""

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        yield PreparedTriageSession(cwd=app_root)

    def run_session(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> TriageSessionResult:
        return TriageSessionResult(success=True, returncode=0, stderr="")


def _seed_repo(factory: ConnectionFactory, name: str = "testrepo") -> int:
    """Insert a repositories row and return its id."""

    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return cur.lastrowid  # type: ignore[return-value]


def _seed(
    run_repo: RunRepository,
    finding_repo: FindingRepository,
    n: int = 1,
    overrides: dict | None = None,
    factory: ConnectionFactory | None = None,
) -> int:
    repo_id: int | None = _seed_repo(factory) if factory is not None else None
    run_id = run_repo.create_run({})
    batch = [
        {
            **_BASE_FINDING,
            "file_path": f"src/file{i}.py",
            **({"repo_id": repo_id} if repo_id is not None else {}),
            **(overrides or {}),
        }
        for i in range(n)
    ]
    finding_repo.insert_findings(run_id, batch)
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
    tmp_path: Path,
    project: str = "testproject",
    *,
    triage_backend: TriageBackendPort | None = None,
    cancel_token=None,
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

    runner = TriageRunner(
        project,
        run_repo,
        triage_repo,
        audit_repo,
        tmp_path,
        tool_registry=MagicMock(),
        triage_backend=triage_backend or _StubTriageAgent(),
        cancel_token=cancel_token,
        session_timeout_seconds=300,
    )
    return runner, factory, run_repo, finding_repo


def _mock_reg(runner: TriageRunner) -> MagicMock:
    return runner._tool_registry  # type: ignore[return-value]


def _parse_ids_from_prompt(prompt: str) -> list[int]:
    match = re.search(r"Finding IDs: \[([^\]]*)\]", prompt)
    assert match is not None, f"Finding IDs not found in prompt: {prompt!r}"
    raw_ids = match.group(1).strip()
    if not raw_ids:
        return []
    return [int(chunk.strip()) for chunk in raw_ids.split(",")]


def _ok_completed(*, stdout: str = "", stderr: str = "") -> MagicMock:
    completed = MagicMock()
    completed.returncode = 0
    completed.stdout = stdout
    completed.stderr = stderr
    return completed


def _make_fake_opencode_run(
    *,
    stdout: str = '{"ok":true}',
    write_updates: bool = True,
    cancel_token: CancellationToken | None = None,
):
    def _fake_run(cmd, **kwargs):
        assert cmd[0] == "opencode"
        assert cmd[1] == "run"
        env = kwargs["env"]
        assert env["OPENCODE_CONFIG"].endswith("opencode.json")
        prompt = kwargs["input"]
        finding_ids = _parse_ids_from_prompt(prompt)
        if write_updates:
            asyncio.run(findings.get_findings_batch(finding_ids))
            updates = [{"finding_id": fid, **_VALID_UPDATE} for fid in finding_ids]
            asyncio.run(findings.update_findings_batch(updates))
        if cancel_token is not None:
            cancel_token.set()
        return _ok_completed(stdout=stdout)

    return _fake_run


def _init_findings_for_triaged_by(
    runner: TriageRunner,
    finding_repo: FindingRepository,
    *,
    project_name: str,
) -> None:
    findings.init(
        FindingsContext(
            finding_repo=finding_repo,
            audit_repo=runner._audit_repo,  # type: ignore[arg-type]
            triage_repo=runner._triage_repo,  # type: ignore[arg-type]
            project_name=project_name,
        )
    )


# Claude session preparation


def test_mcp_json_server_type_is_stdio(tmp_path: Path) -> None:
    _, _, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo)
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="testproject", run_id=42, app_root=tmp_path):
        payload = json.loads((tmp_path / ".mcp.json").read_text())
        assert payload["mcpServers"]["tally-mcp"]["type"] == "stdio"


def test_mcp_json_command_is_venv_python(tmp_path: Path) -> None:
    _make_runner_real(tmp_path)
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="testproject", run_id=42, app_root=tmp_path):
        payload = json.loads((tmp_path / ".mcp.json").read_text())
        expected = str(tmp_path / ".venv" / "bin" / "python")
        assert payload["mcpServers"]["tally-mcp"]["command"] == expected


def test_mcp_json_args_contain_project(tmp_path: Path) -> None:
    _make_runner_real(tmp_path, project="myproject")
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="myproject", run_id=42, app_root=tmp_path):
        payload = json.loads((tmp_path / ".mcp.json").read_text())
        args = payload["mcpServers"]["tally-mcp"]["args"]
        assert "--project" in args
        assert "myproject" in args


def test_mcp_json_only_triage_tools_allowed(tmp_path: Path) -> None:
    _make_runner_real(tmp_path)
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="testproject", run_id=42, app_root=tmp_path):
        payload = json.loads((tmp_path / ".mcp.json").read_text())
        allow = payload["mcpServers"]["tally-mcp"]["permissions"]["allow"]
        assert allow == ["get_findings_batch", "update_findings_batch"]


def test_mcp_json_deny_star(tmp_path: Path) -> None:
    _make_runner_real(tmp_path)
    agent = ClaudeTriageAgent()

    with agent.prepare_session(project="testproject", run_id=42, app_root=tmp_path):
        payload = json.loads((tmp_path / ".mcp.json").read_text())
        deny = payload["mcpServers"]["tally-mcp"]["permissions"]["deny"]
        assert deny == ["*"]


# Group 2: End-to-end pipeline with real store + synthetic handler


def test_pipeline_batch_creates_pending_batches(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
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
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
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
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
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
    assert row["triaged_by"] == "claudecode"


def test_pipeline_audit_log_written(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
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
    _seed(run_repo, finding_repo, factory=factory)

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id, _ = runner.batch()
        result = runner._run_batch_loop(run_id, handler)

    assert isinstance(result, TriageResult)
    assert result.sessions_run == 1
    assert result.success == 1


# Group 3: Multi-batch regression (double-claiming fix)


def test_all_batches_processed_no_stuck_in_progress(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    # Seed 2 findings in different files so batching produces 2+ batches
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/alpha.py", "repo_id": repo_id},
            {
                **_BASE_FINDING,
                "file_path": "src/beta.py",
                "rule_id": "python.xss",
                "repo_id": repo_id,
            },
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
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
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/a.py", "repo_id": repo_id},
            {
                **_BASE_FINDING,
                "file_path": "src/b.py",
                "rule_id": "python.xss",
                "repo_id": repo_id,
            },
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    original_claim = runner._triage_repo.claim_batch
    claim_calls: list[object] = []

    def spy_claim(run_id: int) -> TriageBatchRow | None:
        result = original_claim(run_id)
        claim_calls.append(result)
        return result

    runner._triage_repo.claim_batch = spy_claim  # type: ignore[method-assign]

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id2, total_batches = runner.batch()
        runner._run_batch_loop(run_id2, handler)

    # N batches + 1 None sentinel
    assert len(claim_calls) == total_batches + 1
    assert claim_calls[-1] is None


def test_both_findings_enriched(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(tmp_path)
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        [
            {**_BASE_FINDING, "file_path": "src/a.py", "repo_id": repo_id},
            {
                **_BASE_FINDING,
                "file_path": "src/b.py",
                "rule_id": "python.xss",
                "repo_id": repo_id,
            },
        ],
    )

    mock_semgrep = _make_mock_semgrep()
    handler = _make_synthetic_handler()

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        run_id2, _ = runner.batch()
        runner._run_batch_loop(run_id2, handler)

    with factory.connect() as conn:
        rows = conn.execute("SELECT enriched, triaged_by FROM findings").fetchall()
    assert all(r["enriched"] == 1 for r in rows)
    assert all(r["triaged_by"] == "claudecode" for r in rows)


# Group 4: OpenCode parity


def test_opencode_multi_batch_marks_all_findings(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(
        tmp_path,
        triage_backend=OpenCodeTriageAgent(),
    )
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        [
            {
                **_BASE_FINDING,
                "file_path": f"/src/file{i}.py",
                "rule_id": f"python.rule{i}",
                "repo_id": repo_id,
            }
            for i in range(11)
        ],
    )
    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        with patch.dict("os.environ", {"TALLY_TRIAGED_BY": "opencode"}):
            _init_findings_for_triaged_by(
                runner,
                finding_repo,
                project_name="testproject",
            )
            mock_reg.get_all_tools.return_value = []
            mock_reg.get_tool.return_value = mock_semgrep
            with patch("subprocess.run", side_effect=_make_fake_opencode_run()):
                result = runner.run()

    with factory.connect() as conn:
        rows = conn.execute(
            "SELECT enriched, triaged_by FROM findings ORDER BY id"
        ).fetchall()
        batches = conn.execute(
            "SELECT status FROM triage_batches ORDER BY id"
        ).fetchall()
    assert result.sessions_run > 1
    assert result.success == result.sessions_run
    assert all(r["enriched"] == 1 for r in rows)
    assert all(r["triaged_by"] == "opencode" for r in rows)
    assert all(r["status"] == "success" for r in batches)


def test_opencode_session_incomplete_without_audit_writes(tmp_path: Path) -> None:
    runner, factory, run_repo, finding_repo = _make_runner_real(
        tmp_path,
        triage_backend=OpenCodeTriageAgent(),
    )
    _seed(run_repo, finding_repo, factory=factory)
    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        with patch(
            "subprocess.run",
            side_effect=_make_fake_opencode_run(
                stdout='{"assistant":"updated findings"}',
                write_updates=False,
            ),
        ):
            result = runner.run()

    with factory.connect() as conn:
        row = conn.execute(
            "SELECT enriched, triaged_by FROM findings LIMIT 1"
        ).fetchone()
        audits = conn.execute(
            "SELECT COUNT(*) AS n FROM tool_audit_log WHERE tool_name IN "
            "('update_finding', 'update_findings_batch')"
        ).fetchone()
    assert result.sessions_run == 1
    assert result.success == 0
    assert result.incomplete == 1
    assert row["enriched"] == 0
    assert row["triaged_by"] is None
    assert audits["n"] == 0


def test_opencode_cancel_marks_remaining_batches_cancelled(tmp_path: Path) -> None:
    cancel_token = CancellationToken()
    runner, factory, run_repo, finding_repo = _make_runner_real(
        tmp_path,
        triage_backend=OpenCodeTriageAgent(),
        cancel_token=cancel_token,
    )
    repo_id = _seed_repo(factory)
    seed_run_id = run_repo.create_run({})
    finding_repo.insert_findings(
        seed_run_id,
        [
            {
                **_BASE_FINDING,
                "file_path": f"/src/file{i}.py",
                "rule_id": f"python.rule{i}",
                "repo_id": repo_id,
            }
            for i in range(11)
        ],
    )
    mock_semgrep = _make_mock_semgrep()
    mock_reg = _mock_reg(runner)
    if True:
        with patch.dict("os.environ", {"TALLY_TRIAGED_BY": "opencode"}):
            _init_findings_for_triaged_by(
                runner,
                finding_repo,
                project_name="testproject",
            )
            mock_reg.get_all_tools.return_value = []
            mock_reg.get_tool.return_value = mock_semgrep
            with patch(
                "subprocess.run",
                side_effect=_make_fake_opencode_run(cancel_token=cancel_token),
            ):
                with pytest.raises(TriageCancelled):
                    runner.run()

    with factory.connect() as conn:
        rows = conn.execute("SELECT status FROM triage_batches ORDER BY id").fetchall()
    statuses = [r["status"] for r in rows]
    assert statuses.count("success") == 1
    assert statuses.count("cancelled") >= 1
