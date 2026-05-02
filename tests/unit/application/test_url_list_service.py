"""Unit tests for ``application.url_inventory.url_list_service``."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from application.url_inventory.service import UrlInventoryService
from application.url_inventory.url_list_service import (
    ProjectNotFound,
    UrlListService,
)
from domain.projects.entry import ProjectRow


@dataclass
class _Repo:
    id: int | None
    name: str | None


class _StubUrlRepo:
    def __init__(
        self,
        *,
        active_count: int = 0,
        raises: Exception | None = None,
    ) -> None:
        self._active_count = active_count
        self._raises = raises
        self.count_active_calls = 0

    def count_active(self) -> int:
        self.count_active_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._active_count

    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "UrlListService unit tests should not invoke other port methods"
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
    url_repo: _StubUrlRepo | None = None,
    project_repo: _StubProjectRepo | None = None,
    findings_db_exists: bool = True,
) -> UrlListService:
    if url_repo is None:
        url_repo = _StubUrlRepo()
    if project_repo is None:
        project_repo = _StubProjectRepo()
    inventory = UrlInventoryService(url_repo)  # type: ignore[arg-type]
    return UrlListService(
        url_repo=url_repo,  # type: ignore[arg-type]
        project_repo=project_repo,  # type: ignore[arg-type]
        inventory=inventory,
        findings_db_exists=findings_db_exists,
    )


class TestUrlListService:
    def test_url_repo_property_exposes_constructed_handle(self) -> None:
        url_repo = _StubUrlRepo()
        service = _build(url_repo=url_repo)
        assert service.url_repo is url_repo

    def test_inventory_property_exposes_constructed_handle(self) -> None:
        service = _build()
        assert isinstance(service.inventory, UrlInventoryService)

    def test_for_project_raises_when_project_missing(self) -> None:
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            UrlListService.for_project(registry, 7)  # type: ignore[arg-type]

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
            UrlListService.for_project(registry, 7)  # type: ignore[arg-type]

    def test_repo_name_lookup_returns_empty_when_findings_db_missing(self) -> None:
        project_repo = _StubProjectRepo(rows=[_Repo(id=1, name="r1")])
        service = _build(project_repo=project_repo, findings_db_exists=False)
        assert service.repo_name_lookup() == {}
        assert project_repo.list_active_calls == 0

    def test_repo_name_lookup_returns_empty_on_repo_exception(self) -> None:
        service = _build(project_repo=_StubProjectRepo(raises=RuntimeError("db gone")))
        assert service.repo_name_lookup() == {}

    def test_repo_name_lookup_filters_rows_with_missing_id_or_name(self) -> None:
        rows = [
            _Repo(id=1, name="alpha"),
            _Repo(id=None, name="orphan"),
            _Repo(id=2, name=None),
            _Repo(id=3, name=""),
            _Repo(id=4, name="delta"),
        ]
        service = _build(project_repo=_StubProjectRepo(rows=rows))
        assert service.repo_name_lookup() == {1: "alpha", 4: "delta"}

    def test_count_active_url_findings_returns_zero_when_db_missing(self) -> None:
        url_repo = _StubUrlRepo(active_count=42)
        service = _build(url_repo=url_repo, findings_db_exists=False)
        assert service.count_active_url_findings() == 0
        assert url_repo.count_active_calls == 0

    def test_count_active_url_findings_returns_zero_on_repo_exception(self) -> None:
        url_repo = _StubUrlRepo(raises=RuntimeError("db gone"))
        service = _build(url_repo=url_repo)
        assert service.count_active_url_findings() == 0

    def test_count_active_url_findings_returns_underlying_value(self) -> None:
        url_repo = _StubUrlRepo(active_count=17)
        service = _build(url_repo=url_repo)
        assert service.count_active_url_findings() == 17
        assert url_repo.count_active_calls == 1
