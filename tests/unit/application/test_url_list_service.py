"""Unit tests for ``application.url_inventory.url_list_service``."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from application.url_inventory.service import UrlInventoryService
from application.url_inventory.url_list_service import UrlListService
from core.project_paths import ProjectPaths
from domain.projects.entry import ProjectRow
from factories.persistence import ProjectNotFound


class _StubConverter:
    """No-op stand-in for UrlSourceConverterPort."""

    def to_oas3(self, source_path: Path) -> dict[str, Any]:
        return {}


@dataclass
class _Repo:
    id: int | None
    name: str | None


class _StubUrlRepo:
    def __init__(
        self,
        *,
        active_count: int = 0,
        all_count: int = 0,
        delete_for_tools_return: int = 0,
        raises: Exception | None = None,
        count_all_raises: Exception | None = None,
        delete_for_tools_raises: Exception | None = None,
        list_for_repo_rows: dict[int, list[Any]] | None = None,
        list_for_repo_raises: Exception | None = None,
    ) -> None:
        self._active_count = active_count
        self._all_count = all_count
        self._delete_for_tools_return = delete_for_tools_return
        self._raises = raises
        self._count_all_raises = count_all_raises
        self._delete_for_tools_raises = delete_for_tools_raises
        self._list_for_repo_rows = list_for_repo_rows or {}
        self._list_for_repo_raises = list_for_repo_raises
        self.count_active_calls = 0
        self.count_all_calls = 0
        self.delete_for_tools_calls: list[list[str]] = []
        self.list_for_repo_calls: list[int] = []

    def count_active(self) -> int:
        self.count_active_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._active_count

    def count_all(self) -> int:
        self.count_all_calls += 1
        if self._count_all_raises is not None:
            raise self._count_all_raises
        return self._all_count

    def delete_for_tools(self, tools: list[str]) -> int:
        self.delete_for_tools_calls.append(list(tools))
        if self._delete_for_tools_raises is not None:
            raise self._delete_for_tools_raises
        return self._delete_for_tools_return

    def list_for_repo(self, repo_id: int) -> list[Any]:
        self.list_for_repo_calls.append(repo_id)
        if self._list_for_repo_raises is not None:
            raise self._list_for_repo_raises
        return list(self._list_for_repo_rows.get(repo_id, []))

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
        self.regenerate_calls: list[dict[str, Any]] = []

    def ingest_user_file(
        self, *, repo_id: int, file_path: str, entries: Iterable[Any]
    ) -> int:
        items = list(entries)
        self.ingest_calls.append(
            {"repo_id": repo_id, "file_path": file_path, "entries": items}
        )
        return len(items)

    def regenerate_artifacts(self, **kwargs: Any) -> tuple[str, str]:
        self.regenerate_calls.append(kwargs)
        return ("/fake/seeds.txt", "/fake/oas3.json")


def _build(
    *,
    url_repo: _StubUrlRepo | None = None,
    project_repo: _StubProjectRepo | None = None,
    findings_db_exists: bool = True,
    paths: ProjectPaths | None = None,
    project_name: str = "test-project",
    inventory: Any = None,
    converter: Any = None,
) -> UrlListService:
    if url_repo is None:
        url_repo = _StubUrlRepo()
    if project_repo is None:
        project_repo = _StubProjectRepo()
    if inventory is None:
        inventory = UrlInventoryService(url_repo)  # type: ignore[arg-type]
    if paths is None:
        paths = ProjectPaths(Path("/tmp/url-list-svc-test"))
    if converter is None:
        converter = _StubConverter()
    return UrlListService(
        url_repo=url_repo,  # type: ignore[arg-type]
        project_repo=project_repo,  # type: ignore[arg-type]
        inventory=inventory,
        converter=converter,
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

    def test_factory_raises_when_project_missing(self) -> None:
        from factories.persistence import create_url_list_service

        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: None)
        with pytest.raises(ProjectNotFound):
            create_url_list_service(registry, 7)  # type: ignore[arg-type]

    def test_factory_raises_when_project_archived(self) -> None:
        from factories.persistence import create_url_list_service

        archived = ProjectRow(
            id=7,
            name="p",
            path="/tmp/p",
            created_at="2026-05-01T00:00:00Z",
            archived_at="2026-05-01T00:00:00Z",
        )
        registry = SimpleNamespace(resolve_by_id=lambda _project_id=None: archived)
        with pytest.raises(ProjectNotFound):
            create_url_list_service(registry, 7)  # type: ignore[arg-type]

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


class TestUrlListServiceRepoHasUrlFindings:
    def test_returns_true_when_repo_has_rows(self) -> None:
        url_repo = _StubUrlRepo(list_for_repo_rows={42: [object(), object()]})
        service = _build(url_repo=url_repo)
        assert service.repo_has_url_findings(42) is True
        assert url_repo.list_for_repo_calls == [42]

    def test_returns_false_when_repo_has_no_rows(self) -> None:
        url_repo = _StubUrlRepo(list_for_repo_rows={})
        service = _build(url_repo=url_repo)
        assert service.repo_has_url_findings(42) is False
        assert url_repo.list_for_repo_calls == [42]

    def test_returns_false_when_findings_db_missing(self) -> None:
        url_repo = _StubUrlRepo(list_for_repo_rows={42: [object()]})
        service = _build(url_repo=url_repo, findings_db_exists=False)
        assert service.repo_has_url_findings(42) is False
        assert url_repo.list_for_repo_calls == []

    def test_returns_false_when_repo_raises(self) -> None:
        url_repo = _StubUrlRepo(list_for_repo_raises=RuntimeError("db gone"))
        service = _build(url_repo=url_repo)
        assert service.repo_has_url_findings(42) is False
        assert url_repo.list_for_repo_calls == [42]


class TestUrlListServiceCountAllUrlFindings:
    def test_forwards_to_repo_count_all(self) -> None:
        url_repo = _StubUrlRepo(all_count=23)
        service = _build(url_repo=url_repo)
        assert service.count_all_url_findings() == 23
        assert url_repo.count_all_calls == 1

    def test_returns_zero_when_findings_db_missing(self) -> None:
        url_repo = _StubUrlRepo(all_count=23)
        service = _build(url_repo=url_repo, findings_db_exists=False)
        assert service.count_all_url_findings() == 0
        assert url_repo.count_all_calls == 0

    def test_returns_zero_when_repo_raises(self) -> None:
        url_repo = _StubUrlRepo(count_all_raises=RuntimeError("db gone"))
        service = _build(url_repo=url_repo)
        assert service.count_all_url_findings() == 0


class TestUrlListServiceDeleteUrlFindingsForTools:
    def test_forwards_tools_to_repo(self) -> None:
        url_repo = _StubUrlRepo(delete_for_tools_return=4)
        service = _build(url_repo=url_repo)
        assert service.delete_url_findings_for_tools(["katana", "noir"]) == 4
        assert url_repo.delete_for_tools_calls == [["katana", "noir"]]

    def test_empty_tools_is_no_op(self) -> None:
        url_repo = _StubUrlRepo(delete_for_tools_return=99)
        service = _build(url_repo=url_repo)
        assert service.delete_url_findings_for_tools([]) == 0
        assert url_repo.delete_for_tools_calls == []

    def test_returns_zero_when_findings_db_missing(self) -> None:
        url_repo = _StubUrlRepo(delete_for_tools_return=99)
        service = _build(url_repo=url_repo, findings_db_exists=False)
        assert service.delete_url_findings_for_tools(["katana"]) == 0
        assert url_repo.delete_for_tools_calls == []

    def test_returns_zero_when_repo_raises(self) -> None:
        url_repo = _StubUrlRepo(delete_for_tools_raises=RuntimeError("db gone"))
        service = _build(url_repo=url_repo)
        assert service.delete_url_findings_for_tools(["katana"]) == 0


class _StubInventoryWithDelete:
    """Records ``delete_for_project`` calls."""

    def __init__(self, *, return_value: int = 0, raises: Exception | None = None):
        self._return_value = return_value
        self._raises = raises
        self.delete_for_project_calls = 0

    def delete_for_project(self) -> int:
        self.delete_for_project_calls += 1
        if self._raises is not None:
            raise self._raises
        return self._return_value


class TestUrlListServicePurgeAllUrlFindings:
    def test_forwards_to_inventory_delete_for_project(self) -> None:
        inventory = _StubInventoryWithDelete(return_value=12)
        service = _build(inventory=inventory)
        assert service.purge_all_url_findings() == 12
        assert inventory.delete_for_project_calls == 1

    def test_returns_zero_when_findings_db_missing(self) -> None:
        inventory = _StubInventoryWithDelete(return_value=12)
        service = _build(inventory=inventory, findings_db_exists=False)
        assert service.purge_all_url_findings() == 0
        assert inventory.delete_for_project_calls == 0

    def test_returns_zero_when_inventory_raises(self) -> None:
        inventory = _StubInventoryWithDelete(raises=RuntimeError("db gone"))
        service = _build(inventory=inventory)
        assert service.purge_all_url_findings() == 0


class _FakeUserFileProvider:
    """Stand-in for ``UserFileProvider`` injected via monkeypatch."""

    instances: list[_FakeUserFileProvider] = []
    _next_entries: list[Any] = []

    def __init__(self, _converter: Any = None) -> None:
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
        self.base_urls: list[str] = []


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
