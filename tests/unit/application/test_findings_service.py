"""Unit tests for ``application.findings.findings_service.FindingsService``."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from application.findings.analyst_service import FindingAnalystService
from application.findings.findings_service import (
    FindingsService,
    ProjectNotFound,
)


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
        findings_db_exists=findings_db_exists,
    )
    return service, project_repo


class TestFindingsService:
    def test_from_request_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(project_registry=registry))
        )
        with pytest.raises(ProjectNotFound):
            FindingsService.from_request(request, 7)  # type: ignore[arg-type]

    def test_from_request_raises_when_project_archived(self) -> None:
        archived = {
            "id": 7,
            "name": "p",
            "path": "/tmp/p",
            "archived_at": "2026-05-01T00:00:00Z",
        }
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(project_registry=registry))
        )
        with pytest.raises(ProjectNotFound):
            FindingsService.from_request(request, 7)  # type: ignore[arg-type]

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
