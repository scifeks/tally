"""Unit tests for ``application.url_inventory.url_list_service``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from application.url_inventory.service import UrlInventoryService
from application.url_inventory.url_list_service import (
    ProjectNotFound,
    UrlListService,
)
from core.project_paths import ProjectPaths
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
        self.set_url_seed_file_calls: list[tuple[int, str | None]] = []

    def list_active(self) -> list[_Repo]:
        self.list_active_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._rows

    def set_url_seed_file(self, repo_id: int, path: str | None) -> None:
        self.set_url_seed_file_calls.append((repo_id, path))


class _StubInventory:
    """Records ingest_user_file calls without touching a real repo."""

    def __init__(self) -> None:
        self.ingest_calls: list[dict[str, Any]] = []

    def ingest_user_file(
        self, *, repo_id: int, file_path: str, entries: Iterable[Any]
    ) -> int:
        items = list(entries)
        self.ingest_calls.append(
            {"repo_id": repo_id, "file_path": file_path, "entries": items}
        )
        return len(items)


def _build(
    *,
    url_repo: _StubUrlRepo | None = None,
    project_repo: _StubProjectRepo | None = None,
    findings_db_exists: bool = True,
    paths: ProjectPaths | None = None,
    project_name: str = "test-project",
    inventory: Any = None,
) -> UrlListService:
    if url_repo is None:
        url_repo = _StubUrlRepo()
    if project_repo is None:
        project_repo = _StubProjectRepo()
    if inventory is None:
        inventory = UrlInventoryService(url_repo)  # type: ignore[arg-type]
    if paths is None:
        paths = ProjectPaths(Path("/tmp/url-list-svc-test"))
    return UrlListService(
        url_repo=url_repo,  # type: ignore[arg-type]
        project_repo=project_repo,  # type: ignore[arg-type]
        inventory=inventory,
        findings_db_exists=findings_db_exists,
        paths=paths,
        project_name=project_name,
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


class _FakeUserFileProvider:
    """Stand-in for ``UserFileProvider`` injected via monkeypatch."""

    instances: list[_FakeUserFileProvider] = []
    _next_entries: list[Any] = []

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        type(self).instances.append(self)

    def provide(self, ctx: Any, *, file_path: str) -> Iterable[Any]:
        self.calls.append({"ctx": ctx, "file_path": file_path})
        return list(type(self)._next_entries)

    @classmethod
    def reset(cls, entries: list[Any] | None = None) -> None:
        cls.instances = []
        cls._next_entries = entries or []


class _FakeRepository:
    """Minimal Repository-shaped object the service treats as a Repository."""

    def __init__(self, name: str) -> None:
        self.name = name


class TestUrlListServiceIngestUploadedEndpointFile:
    @pytest.fixture(autouse=True)
    def _patch_provider(self, monkeypatch: pytest.MonkeyPatch) -> Iterable[None]:
        _FakeUserFileProvider.reset(entries=[object(), object()])
        monkeypatch.setattr(
            "application.url_inventory.url_list_service.UserFileProvider",
            _FakeUserFileProvider,
        )
        yield

    def test_writes_upload_under_seed_upload_dir(self, tmp_path: Path) -> None:
        paths = ProjectPaths(tmp_path / "projects" / "demo")
        inventory = _StubInventory()
        service = _build(
            project_repo=_StubProjectRepo(),
            inventory=inventory,
            paths=paths,
            project_name="demo",
        )
        service.ingest_uploaded_endpoint_file(
            repo=_FakeRepository(name="api"),  # type: ignore[arg-type]
            repo_id=11,
            filename="spec.json",
            contents=b'{"openapi":"3.0.0"}',
        )
        candidates = list(paths.endpoints_dir.iterdir())
        assert len(candidates) == 1
        upload_dir = candidates[0]
        assert upload_dir.is_dir()
        assert upload_dir.name.startswith("api-")
        dest = upload_dir / "spec.json"
        assert dest.read_bytes() == b'{"openapi":"3.0.0"}'

    def test_records_seed_file_pointer_with_destination_path(
        self, tmp_path: Path
    ) -> None:
        paths = ProjectPaths(tmp_path / "projects" / "demo")
        project_repo = _StubProjectRepo()
        service = _build(
            project_repo=project_repo,
            inventory=_StubInventory(),
            paths=paths,
            project_name="demo",
        )
        service.ingest_uploaded_endpoint_file(
            repo=_FakeRepository(name="api"),  # type: ignore[arg-type]
            repo_id=42,
            filename="spec.json",
            contents=b"{}",
        )
        assert len(project_repo.set_url_seed_file_calls) == 1
        repo_id, recorded_path = project_repo.set_url_seed_file_calls[0]
        assert repo_id == 42
        assert recorded_path is not None
        assert recorded_path.endswith("/spec.json")
        assert Path(recorded_path).exists()

    def test_invokes_user_file_provider_with_built_context(
        self, tmp_path: Path
    ) -> None:
        paths = ProjectPaths(tmp_path / "root" / "projects" / "demo")
        repo = _FakeRepository(name="api")
        service = _build(
            project_repo=_StubProjectRepo(),
            inventory=_StubInventory(),
            paths=paths,
            project_name="demo",
        )
        service.ingest_uploaded_endpoint_file(
            repo=repo,  # type: ignore[arg-type]
            repo_id=7,
            filename="spec.json",
            contents=b"{}",
        )
        assert len(_FakeUserFileProvider.instances) == 1
        provider = _FakeUserFileProvider.instances[0]
        assert len(provider.calls) == 1
        ctx = provider.calls[0]["ctx"]
        assert ctx.repo is repo
        assert ctx.repo_id == 7
        assert ctx.project_name == "demo"
        assert ctx.run_id is None
        # base_path is two parents up from the project root.
        assert ctx.base_path == str(tmp_path / "root")
        # file_path matches the dest written to disk.
        assert provider.calls[0]["file_path"].endswith("/spec.json")

    def test_calls_inventory_ingest_with_provider_entries(self, tmp_path: Path) -> None:
        sentinel_entries = [object(), object(), object()]
        _FakeUserFileProvider.reset(entries=sentinel_entries)
        paths = ProjectPaths(tmp_path / "projects" / "demo")
        inventory = _StubInventory()
        service = _build(
            project_repo=_StubProjectRepo(),
            inventory=inventory,
            paths=paths,
            project_name="demo",
        )
        service.ingest_uploaded_endpoint_file(
            repo=_FakeRepository(name="api"),  # type: ignore[arg-type]
            repo_id=3,
            filename="spec.json",
            contents=b"{}",
        )
        assert len(inventory.ingest_calls) == 1
        call = inventory.ingest_calls[0]
        assert call["repo_id"] == 3
        assert call["file_path"].endswith("/spec.json")
        assert call["entries"] == sentinel_entries
