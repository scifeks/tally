"""Per-finding loop orchestration tests for TriageRunner.

Covers the per-finding iteration in _run_batch_findings, batch
completion outcome propagation through run(), and the cooperative
cancellation path.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.locking.cancellation import CancellationToken
from application.ports.triage_agent import PreparedTriageSession
from application.triage.runner import (
    TriageCancelled,
    TriageRunner,
)
from application.triage.verdict import (
    Verdict,
    VerdictParseError,
)
from domain.pipeline.triage_events import (
    RunCancelled,
    RunCompleted,
    RunStarted,
)
from domain.triage.entry import TriageBatchRow

# Helpers


def _make_verdict(finding_id: int) -> Verdict:
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


class _PerFindingBackend:
    """Returns a verdict whose finding_id matches each call."""

    def __init__(self, *, prepared_cwd: Path | None = None) -> None:
        self._prepared_cwd = prepared_cwd
        self.calls: list[tuple[str, int, int, Path]] = []

    @contextmanager
    def prepare_session(self, *, project: str, run_id: int, app_root: Path):
        del project, run_id
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
        return _make_verdict(finding_id)


class _FailingBackend(_PerFindingBackend):
    """Raises on specified finding_ids, succeeds on the rest."""

    def __init__(
        self,
        fail_ids: dict[int, BaseException],
        *,
        prepared_cwd: Path | None = None,
    ) -> None:
        super().__init__(prepared_cwd=prepared_cwd)
        self._fail_ids = fail_ids

    def run_triage(
        self,
        prompt: str,
        *,
        finding_id: int,
        timeout_seconds: int,
        cwd: Path,
    ) -> Verdict:
        self.calls.append((prompt, finding_id, timeout_seconds, cwd))
        exc = self._fail_ids.get(finding_id)
        if exc is not None:
            raise exc
        return _make_verdict(finding_id)


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def emit(self, event: object) -> None:
        self.events.append(event)


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


def _make_runner(
    tmp_path: Path,
    *,
    agent: _PerFindingBackend | _FailingBackend | None = None,
    finding_repo: MagicMock | None = None,
    event_sink: _RecordingSink | None = None,
    cancel_token: CancellationToken | None = None,
) -> tuple[
    TriageRunner,
    MagicMock,
    _PerFindingBackend | _FailingBackend,
]:
    store = MagicMock()
    store.latest_run_id.return_value = 1
    store.reset_stale_batches.return_value = 0
    store.get_active_finding_combos.return_value = []

    backend = agent or _PerFindingBackend(prepared_cwd=tmp_path)
    fr = finding_repo or MagicMock()
    fr.update_finding.return_value = True

    runner = TriageRunner(
        "proj",
        store,
        store,
        None,
        tmp_path,
        triage_backend=backend,
        session_timeout_seconds=300,
        retry_count=0,
        tool_registry=MagicMock(),
        finding_repo=fr,
        repo_paths={},
        triaged_by="claudecode",
        event_sink=event_sink,
        cancel_token=cancel_token,
    )
    return runner, store, backend


def _mock_reg(runner: TriageRunner) -> MagicMock:
    return runner._tool_registry  # type: ignore[return-value]


# Tests


def test_multi_finding_batch_calls_adapter_and_writes_verdicts(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    agent = _PerFindingBackend(prepared_cwd=tmp_path)
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data: list[dict[str, Any]] = [
        {"id": 10, "tool": "semgrep", "file": "a.py", "repo": "r"},
        {"id": 20, "tool": "semgrep", "file": "b.py", "repo": "r"},
        {"id": 30, "tool": "semgrep", "file": "c.py", "repo": "r"},
    ]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "success"
    assert len(agent.calls) == 3
    assert [c[1] for c in agent.calls] == [10, 20, 30]
    assert finding_repo.update_finding.call_count == 3
    written_ids = [c.args[0] for c in finding_repo.update_finding.call_args_list]
    assert written_ids == [10, 20, 30]


def test_parse_failure_does_not_abort_remaining_findings(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    agent = _FailingBackend(
        {1: VerdictParseError("bad json")},
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data: list[dict[str, Any]] = [
        {"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"},
        {"id": 2, "tool": "semgrep", "file": "b.py", "repo": "r"},
        {"id": 3, "tool": "semgrep", "file": "c.py", "repo": "r"},
    ]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "incomplete"
    assert len(agent.calls) == 3
    assert finding_repo.update_finding.call_count == 2
    written_ids = [c.args[0] for c in finding_repo.update_finding.call_args_list]
    assert written_ids == [2, 3]


def test_generic_exception_does_not_abort_remaining_findings(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    agent = _FailingBackend(
        {2: RuntimeError("agent crashed")},
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data: list[dict[str, Any]] = [
        {"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"},
        {"id": 2, "tool": "semgrep", "file": "b.py", "repo": "r"},
        {"id": 3, "tool": "semgrep", "file": "c.py", "repo": "r"},
    ]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "incomplete"
    assert len(agent.calls) == 3
    assert finding_repo.update_finding.call_count == 2
    written_ids = [c.args[0] for c in finding_repo.update_finding.call_args_list]
    assert written_ids == [1, 3]


def test_all_findings_fail_returns_failed(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    agent = _FailingBackend(
        {
            1: VerdictParseError("bad"),
            2: VerdictParseError("bad"),
        },
        prepared_cwd=tmp_path,
    )
    runner, _, _ = _make_runner(tmp_path, agent=agent, finding_repo=finding_repo)

    batch_data: list[dict[str, Any]] = [
        {"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"},
        {"id": 2, "tool": "semgrep", "file": "b.py", "repo": "r"},
    ]
    outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

    assert outcome == "failed"
    assert len(agent.calls) == 2
    finding_repo.update_finding.assert_not_called()


def test_run_completes_batch_and_emits_events(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    sink = _RecordingSink()
    agent = _PerFindingBackend(prepared_cwd=tmp_path)
    runner, store, _ = _make_runner(
        tmp_path,
        agent=agent,
        finding_repo=finding_repo,
        event_sink=sink,
    )
    store.claim_batch.side_effect = [
        _make_semgrep_batch(1, [10, 20]),
        None,
    ]
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")
    reg = _mock_reg(runner)
    reg.get_all_tools.return_value = []
    reg.get_tool.return_value = mock_semgrep

    result = runner.run()

    assert result.success == 1
    store.complete_batch.assert_called_once_with(1, "success")

    event_types = [type(e).__name__ for e in sink.events]
    assert event_types[0] == "RunStarted"
    assert "BatchStarted" in event_types
    assert "BatchCompleted" in event_types
    assert event_types[-1] == "RunCompleted"

    started = [e for e in sink.events if isinstance(e, RunStarted)]
    assert started[0].scan_run_id == 1

    completed = [e for e in sink.events if isinstance(e, RunCompleted)]
    assert completed[0].processed_count == 1


def test_cancel_during_batch_loop_cleans_up(
    tmp_path: Path,
) -> None:
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True
    sink = _RecordingSink()
    token = CancellationToken()

    agent = _PerFindingBackend(prepared_cwd=tmp_path)
    runner, store, _ = _make_runner(
        tmp_path,
        agent=agent,
        finding_repo=finding_repo,
        event_sink=sink,
        cancel_token=token,
    )

    def _claim_then_cancel(run_id: int) -> TriageBatchRow | None:
        del run_id
        batch = _make_semgrep_batch(1, [10])
        store.claim_batch.side_effect = [None]
        token.set()
        return batch

    store.claim_batch.side_effect = _claim_then_cancel
    mock_semgrep = _make_mock_tool("semgrep", skip=False, scan_segment="sast")
    reg = _mock_reg(runner)
    reg.get_all_tools.return_value = []
    reg.get_tool.return_value = mock_semgrep

    with pytest.raises(TriageCancelled):
        runner.run()

    store.cancel_remaining.assert_called_once_with(1)
    cancelled = [e for e in sink.events if isinstance(e, RunCancelled)]
    assert len(cancelled) == 1
    assert cancelled[0].scan_run_id == 1
