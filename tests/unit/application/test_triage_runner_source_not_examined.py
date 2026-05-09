"""Unit tests for SourceNotExaminedError handling in TriageRunner."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

from application.ports.triage_agent import PreparedTriageSession
from application.triage.runner import TriageRunner
from application.triage.verdict import (
    SourceNotExaminedError,
    Verdict,
)


class _SourceNotExaminedBackend:
    """Backend stub that raises SourceNotExaminedError."""

    def __init__(
        self,
        finding_id: int = 1,
        reason: str = "Read tool not available",
        prepared_cwd: Path | None = None,
    ) -> None:
        self._finding_id = finding_id
        self._reason = reason
        self._prepared_cwd = prepared_cwd
        self.calls: list[tuple[str, int, int, Path]] = []

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
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
        raise SourceNotExaminedError(
            finding_id=self._finding_id,
            reason=self._reason,
            raw_output="",
        )


def _make_runner_with_source_not_examined(
    tmp_path: Path,
    project: str = "proj",
    *,
    finding_id: int = 1,
    reason: str = "Read tool not available",
) -> tuple[TriageRunner, MagicMock, _SourceNotExaminedBackend]:
    """Build a runner with a backend that raises SourceNotExaminedError."""
    store = MagicMock()
    store.latest_run_id.return_value = 1
    store.reset_stale_batches.return_value = 0
    store.get_active_finding_combos.return_value = []

    agent = _SourceNotExaminedBackend(
        finding_id=finding_id,
        reason=reason,
        prepared_cwd=tmp_path,
    )
    finding_repo = MagicMock()
    finding_repo.update_finding.return_value = True

    runner = TriageRunner(
        project,
        store,
        store,
        None,
        tmp_path,
        triage_backend=agent,
        session_timeout_seconds=300,
        retry_count=0,
        tool_registry=MagicMock(),
        finding_repo=finding_repo,
        repo_paths={},
        triaged_by="claudecode",
    )
    return runner, finding_repo, agent  # type: ignore[return-value]


class TestRunBatchFindingsSourceNotExamined:
    def test_source_not_examined_skips_finding_update(
        self,
        tmp_path: Path,
    ) -> None:
        runner, finding_repo, _agent = _make_runner_with_source_not_examined(tmp_path)

        batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
        outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

        finding_repo.update_finding.assert_not_called()
        assert outcome == "failed"

    def test_source_not_examined_no_retry(
        self,
        tmp_path: Path,
    ) -> None:
        runner, _finding_repo, agent = _make_runner_with_source_not_examined(tmp_path)

        batch_data = [{"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"}]
        runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

        assert len(agent.calls) == 1

    def test_source_not_examined_with_multiple_findings(
        self,
        tmp_path: Path,
    ) -> None:
        runner, finding_repo, _agent = _make_runner_with_source_not_examined(tmp_path)

        batch_data = [
            {"id": 1, "tool": "semgrep", "file": "a.py", "repo": "r"},
            {"id": 2, "tool": "semgrep", "file": "b.py", "repo": "r"},
        ]
        outcome = runner._run_batch_findings(1, batch_data, "sast", cwd=tmp_path)

        finding_repo.update_finding.assert_not_called()
        assert outcome == "failed"
