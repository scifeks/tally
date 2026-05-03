"""Unit tests for ``application.findings.findings_service.FindingsService``."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.findings.analyst_service import (
    BulkUpdateResult,
    FindingAnalystService,
)
from application.findings.findings_service import (
    FindingsService,
    ProjectNotFound,
)
from application.locking import FindingsBusy, LockQueryService
from application.ports.finding_event_sink import NullFindingEventSink
from domain.findings.entry import Finding
from domain.findings.events import FindingUpdated
from domain.projects.entry import ProjectRow


@dataclass
class _Repo:
    id: int | None
    name: str | None


class _StubFindingRepo:
    """Minimal Protocol satisfaction; no method is exercised in these tests."""

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "FindingsService unit tests should not invoke FindingRepositoryPort"
        )


class _CountingFindingRepo:
    def __init__(
        self,
        *,
        total: int = 0,
        raises: Exception | None = None,
    ) -> None:
        self._total = total
        self._raises = raises
        self.count_findings_calls = 0
        self.last_count_tools: list[str] | None = None
        self.delete_findings_calls: list[list[str] | None] = []

    def count_findings(self, *, tools: list[str] | None = None, **_kwargs: Any) -> int:
        self.count_findings_calls += 1
        self.last_count_tools = tools
        if self._raises is not None:
            raise self._raises
        return self._total

    def delete_findings(self, tools: list[str] | None = None) -> None:
        self.delete_findings_calls.append(tools)
        if self._raises is not None:
            raise self._raises

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "Only count_findings / delete_findings exercised by these tests"
        )


class _StubHistoryRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "FindingsService unit tests should not invoke FindingHistoryRepositoryPort"
        )


class _StubProjectRepo:
    def __init__(
        self,
        rows: list[_Repo] | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._rows = rows or []
        self._raises = raises
        self.list_active_calls = 0

    def list_active(self) -> list[_Repo]:
        self.list_active_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._rows


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[FindingUpdated] = []

    def emit(self, event: FindingUpdated) -> None:
        self.events.append(event)


def _build(
    *,
    project_repo: _StubProjectRepo | None = None,
    findings_db_exists: bool = True,
) -> tuple[FindingsService, _StubProjectRepo]:
    finding_repo = _StubFindingRepo()
    history_repo = _StubHistoryRepo()
    if project_repo is None:
        project_repo = _StubProjectRepo()
    analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
    service = FindingsService(
        finding_repo=finding_repo,  # type: ignore[arg-type]
        history_repo=history_repo,  # type: ignore[arg-type]
        project_repo=project_repo,  # type: ignore[arg-type]
        analyst=analyst,
        lock_query=LockQueryService(),
        project_id=1,
        project_name="p",
        findings_db_exists=findings_db_exists,
        event_sink=NullFindingEventSink(),
    )
    return service, project_repo


def _build_with_analyst(
    analyst: Any,
    *,
    sink: _RecordingSink | None = None,
    project_id: int = 7,
) -> FindingsService:
    finding_repo = _StubFindingRepo()
    history_repo = _StubHistoryRepo()
    project_repo = _StubProjectRepo()
    return FindingsService(
        finding_repo=finding_repo,  # type: ignore[arg-type]
        history_repo=history_repo,  # type: ignore[arg-type]
        project_repo=project_repo,  # type: ignore[arg-type]
        analyst=analyst,
        lock_query=LockQueryService(),
        project_id=project_id,
        project_name="p",
        findings_db_exists=True,
        event_sink=sink or NullFindingEventSink(),
    )


def _make_finding(finding_id: int = 42) -> Finding:
    return Finding(
        id=finding_id,
        fingerprint="fp",
        run_id=1,
        tool="semgrep",
        domain="sast",
        segment="sast",
    )


class TestFindingsService:
    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            FindingsService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_for_project_raises_when_project_archived(self) -> None:
        archived = ProjectRow(
            id=7,
            name="p",
            path="/tmp/p",
            created_at="2026-05-01T00:00:00Z",
            archived_at="2026-05-01T00:00:00Z",
        )
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        with pytest.raises(ProjectNotFound):
            FindingsService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_repo_name_lookup_returns_empty_when_findings_db_missing(self) -> None:
        project_repo = _StubProjectRepo(rows=[_Repo(id=1, name="r1")])
        service, project_repo = _build(
            project_repo=project_repo, findings_db_exists=False
        )
        assert service.repo_name_lookup() == {}
        assert project_repo.list_active_calls == 0

    def test_repo_name_lookup_returns_empty_on_repo_exception(self) -> None:
        project_repo = _StubProjectRepo(raises=RuntimeError("db gone"))
        service, _ = _build(project_repo=project_repo)
        assert service.repo_name_lookup() == {}

    def test_repo_name_lookup_filters_rows_with_missing_id_or_name(self) -> None:
        rows = [
            _Repo(id=1, name="alpha"),
            _Repo(id=None, name="orphan"),
            _Repo(id=2, name=None),
            _Repo(id=3, name=""),
            _Repo(id=4, name="delta"),
        ]
        service, _ = _build(project_repo=_StubProjectRepo(rows=rows))
        assert service.repo_name_lookup() == {1: "alpha", 4: "delta"}

    def test_repo_name_lookup_returns_id_to_name_map(self) -> None:
        rows = [_Repo(id=10, name="r10"), _Repo(id=20, name="r20")]
        service, _ = _build(project_repo=_StubProjectRepo(rows=rows))
        assert service.repo_name_lookup() == {10: "r10", 20: "r20"}

    def test_analyst_property_exposes_built_service(self) -> None:
        service, _ = _build()
        assert isinstance(service.analyst, FindingAnalystService)

    def test_history_repo_property_exposes_port(self) -> None:
        service, _ = _build()
        assert isinstance(service.history_repo, _StubHistoryRepo)

    def test_count_findings_returns_zero_when_findings_db_missing(self) -> None:
        finding_repo = _CountingFindingRepo(total=42)
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=False,
        )
        assert service.count_findings() == 0
        assert finding_repo.count_findings_calls == 0

    def test_count_findings_returns_zero_on_repo_exception(self) -> None:
        finding_repo = _CountingFindingRepo(raises=RuntimeError("db gone"))
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        assert service.count_findings() == 0

    def test_count_findings_returns_underlying_value(self) -> None:
        finding_repo = _CountingFindingRepo(total=17)
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        assert service.count_findings() == 17
        assert finding_repo.count_findings_calls == 1


class TestFindingsServiceCountFindingsTools:
    def test_forwards_tools_filter_to_repo(self) -> None:
        finding_repo = _CountingFindingRepo(total=8)
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        assert service.count_findings(tools=["semgrep", "gitleaks"]) == 8
        assert finding_repo.last_count_tools == ["semgrep", "gitleaks"]

    def test_returns_zero_when_findings_db_missing_with_tools(self) -> None:
        finding_repo = _CountingFindingRepo(total=8)
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=False,
        )
        assert service.count_findings(tools=["semgrep"]) == 0
        assert finding_repo.count_findings_calls == 0


class TestFindingsServiceDeleteFindingsForTools:
    def test_forwards_tools_to_repo(self) -> None:
        finding_repo = _CountingFindingRepo()
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        service.delete_findings_for_tools(["katana", "noir"])
        assert finding_repo.delete_findings_calls == [["katana", "noir"]]

    def test_empty_tools_is_no_op(self) -> None:
        finding_repo = _CountingFindingRepo()
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        service.delete_findings_for_tools([])
        assert finding_repo.delete_findings_calls == []


class TestFindingsServicePurgeAllFindingsData:
    def test_forwards_to_factory_purge(self) -> None:
        finding_repo = _StubFindingRepo()
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        factory = MagicMock()
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
            factory=factory,
        )
        service.purge_all_findings_data()
        factory.purge_non_preserved_tables.assert_called_once_with()

    def test_no_op_when_factory_not_stored(self) -> None:
        finding_repo = _StubFindingRepo()
        history_repo = _StubHistoryRepo()
        project_repo = _StubProjectRepo()
        analyst = FindingAnalystService(finding_repo)  # type: ignore[arg-type]
        service = FindingsService(
            finding_repo=finding_repo,  # type: ignore[arg-type]
            history_repo=history_repo,  # type: ignore[arg-type]
            project_repo=project_repo,  # type: ignore[arg-type]
            analyst=analyst,
            lock_query=LockQueryService(),
            project_id=1,
            project_name="p",
            findings_db_exists=True,
        )
        # Does not raise.
        service.purge_all_findings_data()


class TestFindingsServicePatch:
    def test_patch_finding_emits_event_and_returns_finding(self) -> None:
        finding = _make_finding()
        analyst = MagicMock(spec=FindingAnalystService)
        analyst.update_fields.return_value = True
        analyst.get_finding.return_value = finding
        sink = _RecordingSink()
        service = _build_with_analyst(analyst, sink=sink, project_id=7)

        result = service.patch_finding(42, {"severity": "critical"})

        assert result is finding
        analyst.update_fields.assert_called_once()
        assert len(sink.events) == 1
        event = sink.events[0]
        assert event.project_id == 7
        assert event.finding is finding

    def test_patch_finding_returns_none_when_not_found(self) -> None:
        analyst = MagicMock(spec=FindingAnalystService)
        analyst.update_fields.return_value = False
        sink = _RecordingSink()
        service = _build_with_analyst(analyst, sink=sink)

        assert service.patch_finding(42, {"severity": "critical"}) is None

        analyst.get_finding.assert_not_called()
        assert sink.events == []

    def test_patch_finding_propagates_findings_busy(self) -> None:
        analyst = MagicMock(spec=FindingAnalystService)
        analyst.update_fields.side_effect = FindingsBusy([42], {42: "x"})
        sink = _RecordingSink()
        service = _build_with_analyst(analyst, sink=sink)

        with pytest.raises(FindingsBusy):
            service.patch_finding(42, {})

        assert sink.events == []

    def test_patch_finding_holder_token_format(self) -> None:
        finding = _make_finding()
        analyst = MagicMock(spec=FindingAnalystService)
        analyst.update_fields.return_value = True
        analyst.get_finding.return_value = finding
        service = _build_with_analyst(analyst)

        service.patch_finding(42, {})

        kwargs = analyst.update_fields.call_args.kwargs
        assert re.fullmatch(r"analyst-patch:[0-9a-f]{8}", kwargs["holder_token"])

    def test_batch_patch_emits_event_per_updated_id(self) -> None:
        finding_a = _make_finding(1)
        finding_b = _make_finding(2)
        analyst = MagicMock(spec=FindingAnalystService)
        bulk = BulkUpdateResult(updated=[1, 2], skipped_locked=[3], not_found=[])
        analyst.bulk_update_fields.return_value = bulk
        analyst.get_finding.side_effect = lambda fid: {1: finding_a, 2: finding_b}[fid]
        sink = _RecordingSink()
        service = _build_with_analyst(analyst, sink=sink, project_id=11)

        result = service.batch_patch_findings([1, 2, 3], {"should_report": 1})

        assert result is bulk
        assert [e.finding.id for e in sink.events] == [1, 2]
        assert all(e.project_id == 11 for e in sink.events)

    def test_batch_patch_holder_token_format(self) -> None:
        analyst = MagicMock(spec=FindingAnalystService)
        analyst.bulk_update_fields.return_value = BulkUpdateResult()
        service = _build_with_analyst(analyst)

        service.batch_patch_findings([], {})

        kwargs = analyst.bulk_update_fields.call_args.kwargs
        assert re.fullmatch(r"analyst-batch:[0-9a-f]{8}", kwargs["holder_token"])
