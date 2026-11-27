"""Tests for ToolRunRecorder state transitions."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.scans.tool_run_recorder import (
    STORAGE_FAILED_REASON,
    ToolRunRecorder,
)
from domain.pipeline import scan_events as se
from domain.pipeline.events import IngestCompleted

_RUN = 5
_ROW = 11
_TOOL = {"repo": "shop", "service": "api", "tool": "semgrep"}


def _recorder(repo_id: int | None = 3) -> tuple[ToolRunRecorder, MagicMock]:
    runs = MagicMock()
    runs.add_tool_run.return_value = _ROW
    repos = MagicMock()
    repos.find_id_by_name.return_value = repo_id
    recorder = ToolRunRecorder(runs, repos, run_id=_RUN, domain_of=lambda tool: "code")
    return recorder, runs


def _event(cls: type, **fields: object) -> se.ScanEvent:
    return cls(run_id=_RUN, project_id=1, timestamp="T1", **_TOOL, **fields)


def _ingest(stored: bool, ids: list[int]) -> IngestCompleted:
    return IngestCompleted(
        ids=ids,
        failed_tools=[],
        run_id=_RUN,
        project_name="proj",
        base_path="/tmp",
        tool="semgrep",
        repo="shop",
        service="api",
        stored=stored,
    )


class TestToolRunRecorder:
    def test_start_inserts_a_running_row(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        runs.add_tool_run.assert_called_once_with(
            run_id=_RUN,
            tool="semgrep",
            repo_id=3,
            service="api",
            domain="code",
            status="running",
            started_at="T1",
            finished_at=None,
            reason=None,
        )

    def test_finished_tool_stays_running_until_findings_are_stored(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        recorder.emit(_event(se.ToolCompleted, exit_code=0))
        runs.update_tool_run.assert_called_once_with(
            _ROW, exit_code=0, finished_at="T1"
        )

    @pytest.mark.parametrize(
        ("stored", "ids", "expected"),
        [
            pytest.param(
                True, [1, 2], {"status": "done", "findings_count": 2}, id="ok"
            ),
            pytest.param(True, [], {"status": "done", "findings_count": 0}, id="clean"),
            pytest.param(
                False,
                [],
                {"status": "failed", "reason": STORAGE_FAILED_REASON},
                id="storage-failed",
            ),
        ],
    )
    def test_storage_result_closes_a_running_row(
        self, stored: bool, ids: list[int], expected: dict
    ) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        recorder.on_ingest_completed(_ingest(stored, ids))
        runs.update_tool_run.assert_called_once_with(_ROW, **expected)

    def test_storage_result_cannot_reopen_a_failed_row(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        recorder.emit(_event(se.ToolFailed, message="exit 2", exit_code=2))
        runs.update_tool_run.reset_mock()
        recorder.on_ingest_completed(_ingest(True, []))
        runs.update_tool_run.assert_not_called()

    def test_restart_replaces_the_previous_attempt_row(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        recorder.emit(_event(se.ToolFailed, message="exit 2", exit_code=2))
        runs.add_tool_run.return_value = _ROW + 1
        recorder.emit(
            se.ToolStarted(run_id=_RUN, project_id=1, timestamp="T2", **_TOOL)
        )
        runs.delete_tool_run.assert_called_once_with(_ROW)
        inserted = runs.add_tool_run.call_args.kwargs
        assert (
            inserted["status"],
            inserted["started_at"],
            inserted["finished_at"],
            inserted["reason"],
        ) == ("running", "T2", None, None)

    @pytest.mark.parametrize(
        ("kind", "status"),
        [
            pytest.param(se.SKIP_COULD_NOT_RUN, "failed", id="could-not-run"),
            pytest.param(se.SKIP_DECLINED, "skipped", id="declined"),
        ],
    )
    def test_skip_before_start_inserts_a_closed_row(
        self, kind: str, status: str
    ) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolSkipped, skip_reason="why", kind=kind))
        inserted = runs.add_tool_run.call_args.kwargs
        assert (inserted["status"], inserted["reason"], inserted["finished_at"]) == (
            status,
            "why",
            "T1",
        )

    def test_declined_after_start_closes_the_row_as_skipped(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(_event(se.ToolStarted))
        recorder.emit(
            _event(se.ToolSkipped, skip_reason="declined", kind=se.SKIP_DECLINED)
        )
        runs.update_tool_run.assert_called_once_with(
            _ROW, status="skipped", reason="declined", finished_at="T1"
        )

    def test_not_applicable_leaves_no_row(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(
            _event(se.ToolSkipped, skip_reason="n/a", kind=se.SKIP_NOT_APPLICABLE)
        )
        runs.add_tool_run.assert_not_called()
        recorder.emit(_event(se.ToolStarted))
        recorder.emit(
            _event(se.ToolSkipped, skip_reason="n/a", kind=se.SKIP_NOT_APPLICABLE)
        )
        runs.delete_tool_run.assert_called_once_with(_ROW)

    @pytest.mark.parametrize(
        ("event", "reason"),
        [
            pytest.param(
                se.RunCancelled(run_id=_RUN, project_id=1), "scan cancelled", id="x"
            ),
            pytest.param(
                se.RunFailed(run_id=_RUN, project_id=1), "scan failed", id="f"
            ),
            pytest.param(
                se.RunCompleted(run_id=_RUN, project_id=1),
                "scan ended before the tool finished",
                id="c",
            ),
        ],
    )
    def test_run_end_fails_rows_still_running(
        self, event: se.ScanEvent, reason: str
    ) -> None:
        recorder, runs = _recorder()
        recorder.emit(event)
        runs.fail_running_tool_runs.assert_called_once_with(_RUN, reason)

    def test_empty_repo_and_service_are_stored_as_null(self) -> None:
        recorder, runs = _recorder()
        recorder.emit(
            se.ToolStarted(run_id=_RUN, project_id=1, repo="", service="", tool="burp")
        )
        inserted = runs.add_tool_run.call_args.kwargs
        assert (inserted["repo_id"], inserted["service"]) == (None, None)

    def test_unresolvable_repo_name_writes_no_row(self) -> None:
        recorder, runs = _recorder(repo_id=None)
        recorder.emit(_event(se.ToolStarted))
        runs.add_tool_run.assert_not_called()

    def test_repository_errors_do_not_reach_the_scan(self) -> None:
        recorder, runs = _recorder()
        runs.add_tool_run.side_effect = RuntimeError("db locked")
        recorder.emit(_event(se.ToolStarted))
        recorder.on_ingest_completed(_ingest(True, []))
