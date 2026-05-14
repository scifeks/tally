"""Tests TriageRunner."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.ports.triage_agent import (  # noqa: E402
    PreparedTriageSession,
)
from application.triage.runner import (  # noqa: E402
    TriageResult,
    TriageRunner,
)
from application.triage.verdict import (  # noqa: E402
    Verdict,
    VerdictParseError,
)
from domain.triage.entry import TriageBatchRow  # noqa: E402


def _make_verdict(finding_id: int = 1) -> Verdict:
    return Verdict(
        finding_id=finding_id,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="high",
        reasoning="test reasoning",
        remediation="test remediation",
        attack_vector="test attack vector",
        call_stack=[],
    )


class _StubTriageBackend:
    """Backend stub returning canned Verdicts."""

    def __init__(
        self,
        *,
        verdict: Verdict | None = None,
        side_effect: BaseException | None = None,
        prepared_cwd: Path | None = None,
    ) -> None:
        self._verdict = verdict
        self._side_effect = side_effect
        self._prepared_cwd = prepared_cwd
        self.calls: list[tuple[str, int, int, Path]] = []
        self.prepare_calls: list[tuple[str, int, Path]] = []
        self.last_raw_output: str = ""

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        self.prepare_calls.append((project, run_id, app_root))
        yield PreparedTriageSession(cwd=self._prepared_cwd or app_root)

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        self.calls.append((prompt, finding_id, timeout_seconds, cwd))
        if self._side_effect is not None:
            raise self._side_effect
        assert self._verdict is not None
        return self._verdict


def _make_runner(
    tmp_path: Path,
    project: str = "proj",
    *,
    agent: _StubTriageBackend | None = None,
    finding_repo: MagicMock | None = None,
    repo_paths: dict[str, Path] | None = None,
    retry_count: int = 0,
) -> tuple[TriageRunner, MagicMock, _StubTriageBackend]:
    """Builds a runner with stubbed dependencies."""
    store = MagicMock()
    store.latest_run_id.return_value = 1
    store.cancel_remaining.return_value = 0
    store.get_active_finding_combos.return_value = []

    triage_backend = agent or _StubTriageBackend(
        verdict=_make_verdict(), prepared_cwd=tmp_path
    )
    fr = finding_repo or MagicMock()
    fr.update_finding.return_value = True
    runner = TriageRunner(
        project,
        store,
        store,
        None,
        tmp_path,
        triage_backend=triage_backend,
        session_timeout_seconds=300,
        retry_count=retry_count,
        tool_registry=MagicMock(),
        finding_repo=fr,
        repo_paths=repo_paths or {},
        triaged_by="claudecode",
    )
    return runner, store, triage_backend  # type: ignore[return-value]


def _mock_reg(runner: TriageRunner) -> MagicMock:
    return runner._tool_registry  # type: ignore[return-value]


def _make_mock_tool(name: str, *, skip: bool, scan_segment: str = "sast") -> MagicMock:
    t = MagicMock()
    t.name = name
    t.skip = skip
    t.scan_segment = scan_segment
    return t


def _make_semgrep_batch(batch_id: int, finding_ids: list[int]) -> TriageBatchRow:
    return TriageBatchRow(
        id=batch_id,
        run_id=1,
        finding_ids=finding_ids,
        batch_data=[
            {
                "id": fid,
                "tool": "semgrep",
                "file": f"src/file{fid}.py",
                "repo": "testrepo",
            }
            for fid in finding_ids
        ],
        status="pending",
        run_attempts=0,
        created_at=None,
        started_at=None,
        completed_at=None,
    )


# batch()


def test_batch_resets_stale_before_creating(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = []

    runner.batch()

    store.cancel_remaining.assert_called_once()
    store.create_batches.assert_not_called()


def test_batch_calls_create_per_combo(tmp_path: Path) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = [
        ("semgrep", "repo1", "sast"),
        ("zap", "repo1", "api"),
    ]
    store.fetch_active_findings_for_batching.return_value = []
    store.create_batches.return_value = 2

    run_id, total = runner.batch()

    assert store.fetch_active_findings_for_batching.call_count == 2
    store.fetch_active_findings_for_batching.assert_any_call("semgrep", "repo1", "sast")
    store.fetch_active_findings_for_batching.assert_any_call("zap", "repo1", "api")
    assert store.create_batches.call_count == 2
    for call in store.create_batches.call_args_list:
        assert call.args[0] == run_id
    assert total == 4  # 2 + 2


def test_batch_passes_skip_tools_to_store(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = []
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = [mock_nmap]
        runner.batch()

    skip_tools = store.get_active_finding_combos.call_args[0][0]
    assert "nmap" in skip_tools


def test_batch_resets_before_fetching_combos(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    call_order: list[str] = []
    store.cancel_remaining.side_effect = lambda *a, **k: call_order.append("reset") or 0
    store.get_active_finding_combos.side_effect = lambda *a, **k: (
        call_order.append("combos") or []
    )

    runner.batch()

    assert call_order == ["reset", "combos"]


def test_batch_error_raises_runtime_error(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.get_active_finding_combos.return_value = [("semgrep", "repo1", "sast")]
    store.create_batches.side_effect = RuntimeError("db locked")

    with pytest.raises(RuntimeError, match="Batching failed"):
        runner.batch()


# _run_batch_findings()


def test_run_batch_findings_all_succeed(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    agent = _StubTriageBackend(verdict=_make_verdict(1), prepared_cwd=tmp_path)
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "success"
    finding_repo.update_finding.assert_called_once()


def test_run_batch_findings_all_fail_parse_error(
    tmp_path: Path,
) -> None:
    agent = _StubTriageBackend(
        side_effect=VerdictParseError("bad json"),
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent)

    batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "failed"


def test_run_batch_findings_mixed_outcomes(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    call_count = 0

    class _MixedBackend(_StubTriageBackend):
        def run_triage(self, prompt, *, finding_id, **kw):
            nonlocal call_count
            call_count += 1
            if finding_id == 2:
                raise VerdictParseError("bad")
            return _make_verdict(finding_id)

    agent = _MixedBackend(prepared_cwd=tmp_path)
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data = [
        {"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"},
        {"id": 2, "tool": "semgrep", "file": "b.py", "repo": "r"},
    ]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "incomplete"
    assert finding_repo.update_finding.call_count == 1


def test_run_batch_findings_writes_verdict_fields(
    tmp_path: Path,
) -> None:
    verdict = Verdict(
        finding_id=42,
        confidence="confirmed",
        finding_type="vulnerability",
        severity="critical",
        reasoning="sql injection",
        remediation="use parameterized queries",
        attack_vector="network input",
        call_stack=["main.py:10", "db.py:5"],
    )
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    agent = _StubTriageBackend(verdict=verdict, prepared_cwd=tmp_path)
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data = [
        {
            "id": 42,
            "tool": "semgrep",
            "file": "a.py",
            "repo": "r",
        }
    ]
    runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    finding_repo.update_finding.assert_called_once_with(
        42,
        severity_rank=0,
        confidence="confirmed",
        finding_type_json='["vulnerability"]',
        triage_meta={
            "confidence": "confirmed",
            "reasoning": "sql injection",
            "remediation": "use parameterized queries",
            "attack_vector": "network input",
            "call_stack": '["main.py:10", "db.py:5"]',
        },
        strategy="sast",
        triaged_by="claudecode",
        source="auto_triage",
    )


# _run_batch_findings() retry behavior


def test_retry_succeeds_after_parse_error(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    call_count = 0

    class _FailOnceThenSucceed(_StubTriageBackend):
        def run_triage(self, prompt, *, finding_id, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise VerdictParseError("bad json")
            return _make_verdict(finding_id)

    agent = _FailOnceThenSucceed(prepared_cwd=tmp_path)
    runner, _, _ = _make_runner(
        tmp_path,
        agent=agent,
        finding_repo=finding_repo,
        retry_count=1,
    )

    batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "success"
    assert call_count == 2
    finding_repo.update_finding.assert_called_once()


def test_retries_exhausted_counts_as_failed(
    tmp_path: Path,
) -> None:
    agent = _StubTriageBackend(
        side_effect=VerdictParseError("bad"),
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent, retry_count=2)

    batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "failed"
    assert len(agent.calls) == 3


def test_non_parse_error_not_retried(
    tmp_path: Path,
) -> None:
    agent = _StubTriageBackend(
        side_effect=RuntimeError("boom"),
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent, retry_count=2)

    batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "failed"
    assert len(agent.calls) == 1


# _read_source_file()


def test_read_source_file_returns_contents(
    tmp_path: Path,
) -> None:
    repo_dir = tmp_path / "myrepo"
    repo_dir.mkdir()
    src = repo_dir / "src" / "app.py"
    src.parent.mkdir(parents=True)
    src.write_text("print('hello')")

    runner, _, _ = _make_runner(tmp_path, repo_paths={"myrepo": repo_dir})
    finding: dict[str, Any] = {
        "repo": "myrepo",
        "file": "src/app.py",
    }

    assert runner._read_source_file(finding) == "print('hello')"


def test_read_source_file_missing_repo(
    tmp_path: Path,
) -> None:
    runner, _, _ = _make_runner(tmp_path, repo_paths={})
    finding: dict[str, Any] = {
        "repo": "missing",
        "file": "a.py",
    }

    assert runner._read_source_file(finding) == ""


def test_read_source_file_missing_file(
    tmp_path: Path,
) -> None:
    runner, _, _ = _make_runner(tmp_path, repo_paths={"r": tmp_path})
    finding: dict[str, Any] = {
        "repo": "r",
        "file": "nonexistent.py",
    }

    assert runner._read_source_file(finding) == ""


def test_read_source_file_no_file_field(
    tmp_path: Path,
) -> None:
    runner, _, _ = _make_runner(tmp_path, repo_paths={"r": tmp_path})
    finding: dict[str, Any] = {"repo": "r"}

    assert runner._read_source_file(finding) == ""


# run()


def test_run_calls_batch_then_sessions(
    tmp_path: Path,
) -> None:
    agent = _StubTriageBackend(verdict=_make_verdict(1), prepared_cwd=tmp_path)
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    runner, store, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(1, [1]),
        None,
    ]

    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        result = runner.run()

    store.latest_run_id.assert_called_once()
    assert isinstance(result, TriageResult)
    assert result.sessions_run == 1
    assert result.success == 1
    assert result.failed == 0
    assert result.incomplete == 0


def test_run_skips_skip_strategy_tools(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    nmap_batch = TriageBatchRow(
        id=1,
        run_id=1,
        finding_ids=[1, 2],
        batch_data=[
            {"id": 1, "tool": "nmap"},
            {"id": 2, "tool": "nmap"},
        ],
        status="pending",
        run_attempts=0,
        created_at=None,
        started_at=None,
        completed_at=None,
    )
    store.claim_batch.side_effect = [nmap_batch, None]
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_nmap
        result = runner.run()

    assert result.sessions_run == 0
    store.complete_batch.assert_called_once_with(1, "success")


def test_run_uses_agent_prepared_session_context(
    tmp_path: Path,
) -> None:
    agent = _StubTriageBackend(verdict=_make_verdict(42), prepared_cwd=tmp_path)
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    runner, store, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(1, [42]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run()

    assert agent.prepare_calls == [("proj", 1, tmp_path)]
    assert agent.calls[0][3] == tmp_path


# run_dry_run()


def test_run_dry_run_calls_batch(tmp_path: Path) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.return_value = None
    runner.run_dry_run()
    store.latest_run_id.assert_called_once()


def test_run_dry_run_marks_all_batches_success(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(10, [1, 2]),
        _make_semgrep_batch(11, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run_dry_run()

    assert store.complete_batch.call_count == 2
    store.complete_batch.assert_any_call(10, "success")
    store.complete_batch.assert_any_call(11, "success")


def test_run_dry_run_no_pending_remain(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(5, [1]),
        _make_semgrep_batch(6, [2]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        runner.run_dry_run()

    calls = [c.args for c in store.complete_batch.call_args_list]
    assert all(status == "success" for _, status in calls)


def test_run_dry_run_prompt_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(7, [42]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_all_tools.return_value = []
        mock_reg.get_tool.return_value = mock_semgrep
        with caplog.at_level(
            logging.DEBUG,
            logger="application.triage.runner",
        ):
            runner.run_dry_run()

    log_text = " ".join(r.message for r in caplog.records)
    assert "42" in log_text
    assert "FINDING 42" in log_text


def test_run_dry_run_does_not_call_prepare(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.return_value = None
    from unittest.mock import patch

    with patch.object(runner, "_prepare_session") as mock_prepare:
        runner.run_dry_run()
    mock_prepare.assert_not_called()


# _run_batch_loop()


def _make_nmap_batch(batch_id: int, finding_ids: list[int]) -> TriageBatchRow:
    return TriageBatchRow(
        id=batch_id,
        run_id=1,
        finding_ids=finding_ids,
        batch_data=[{"id": fid, "tool": "nmap"} for fid in finding_ids],
        status="pending",
        run_attempts=0,
        created_at=None,
        started_at=None,
        completed_at=None,
    )


def test_run_batch_loop_skip_completes_without_handler(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_nmap_batch(1, [10, 11]),
        None,
    ]
    mock_nmap = _make_mock_tool("nmap", skip=True, scan_segment="network")

    handler = MagicMock(return_value="success")
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_tool.return_value = mock_nmap
        result = runner._run_batch_loop(1, handler)

    handler.assert_not_called()
    store.complete_batch.assert_called_once_with(1, "success")
    assert result.sessions_run == 0
    assert result.success == 0


def test_run_batch_loop_returns_correct_counts(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(1, [1]),
        _make_semgrep_batch(2, [2]),
        _make_semgrep_batch(3, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    outcomes = ["success", "failed", "incomplete"]
    handler = MagicMock(side_effect=outcomes)
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_tool.return_value = mock_semgrep
        result = runner._run_batch_loop(99, handler)

    assert result.sessions_run == 3
    assert result.success == 1
    assert result.failed == 1
    assert result.incomplete == 1


def test_run_batch_loop_exhausts_all_batches(
    tmp_path: Path,
) -> None:
    runner, store, _ = _make_runner(tmp_path)
    store.claim_batch.side_effect = [
        _make_semgrep_batch(1, [1]),
        _make_semgrep_batch(2, [2]),
        _make_semgrep_batch(3, [3]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")

    handler = MagicMock(return_value="success")
    mock_reg = _mock_reg(runner)
    if True:
        mock_reg.get_tool.return_value = mock_semgrep
        runner._run_batch_loop(99, handler)

    assert store.claim_batch.call_count == 4
    assert handler.call_count == 3
