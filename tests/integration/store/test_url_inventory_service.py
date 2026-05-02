"""Integration tests for application.url_inventory.service (Phase 9 Step 3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.url_inventory.service import UrlInventoryService  # noqa: E402
from core.config.schemas.repository import Repository  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)
from infrastructure.store.repositories.url_findings import (  # noqa: E402
    UrlFindingRepository,
)

pytestmark = pytest.mark.integration


def _repo(name: str) -> Repository:
    return Repository(
        name=name,
        type=["api"],
        languages=["python"],
        docker_path="/app",
        container_name="ctr",
    )


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def repo_id(factory: ConnectionFactory) -> int:
    rr = RepositoryRepository(factory)
    return rr.insert(_repo("alpha"))


@pytest.fixture()
def service(factory: ConnectionFactory) -> UrlInventoryService:
    return UrlInventoryService(UrlFindingRepository(factory))


def _scan(
    repo_id: int,
    *,
    path: str,
    tool: UrlTool = UrlTool.KATANA,
) -> UrlFinding:
    return UrlFinding(
        repo_id=repo_id,
        source=UrlSource.SCAN,
        tool=tool,
        run_id=None,
        method="GET",
        protocol="https",
        host="api.example.com",
        port=443,
        path=path,
    )


def _user(repo_id: int, *, file_path: str, path: str) -> UrlFinding:
    return UrlFinding(
        repo_id=repo_id,
        source=UrlSource.USER,
        tool=None,
        run_id=None,
        method="GET",
        protocol="https",
        host="api.example.com",
        port=443,
        path=path,
        file_path=file_path,
    )


class TestIngestScanSource:
    def test_wipe_and_replace_for_repo_and_tool(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(repo_id, path="/old1"), _scan(repo_id, path="/old2")],
        )
        # Re-ingest with new entries; old katana rows must be wiped.
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(repo_id, path="/new1")],
        )
        repo = UrlFindingRepository(factory)
        rows = repo.list_for_repo(repo_id, source=UrlSource.SCAN)
        assert {r.path for r in rows} == {"/new1"}

    def test_does_not_wipe_other_tool(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(repo_id, path="/k")],
        )
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.NOIR,
            entries=[_scan(repo_id, path="/n", tool=UrlTool.NOIR)],
        )
        # Re-ingest katana; noir rows must stay.
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(repo_id, path="/k2")],
        )
        repo = UrlFindingRepository(factory)
        rows = repo.list_for_repo(repo_id)
        assert {r.path for r in rows} == {"/k2", "/n"}


class TestIngestUserFile:
    def test_wipe_and_replace_for_file(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_user_file(
            repo_id=repo_id,
            file_path="/uploads/v1.json",
            entries=[
                _user(repo_id, file_path="/uploads/v1.json", path="/old"),
            ],
        )
        # Re-upload same file path; old rows wiped.
        service.ingest_user_file(
            repo_id=repo_id,
            file_path="/uploads/v1.json",
            entries=[
                _user(repo_id, file_path="/uploads/v1.json", path="/new"),
            ],
        )
        repo = UrlFindingRepository(factory)
        rows = repo.list_for_repo(repo_id, source=UrlSource.USER)
        assert {r.path for r in rows} == {"/new"}

    def test_does_not_wipe_other_user_files(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_user_file(
            repo_id=repo_id,
            file_path="/uploads/a.json",
            entries=[_user(repo_id, file_path="/uploads/a.json", path="/a")],
        )
        service.ingest_user_file(
            repo_id=repo_id,
            file_path="/uploads/b.json",
            entries=[_user(repo_id, file_path="/uploads/b.json", path="/b")],
        )
        service.ingest_user_file(
            repo_id=repo_id,
            file_path="/uploads/a.json",
            entries=[_user(repo_id, file_path="/uploads/a.json", path="/a-new")],
        )
        repo = UrlFindingRepository(factory)
        rows = repo.list_for_repo(repo_id)
        assert {r.path for r in rows} == {"/a-new", "/b"}


class TestRegenerateArtifacts:
    def test_writes_seeds_and_oas3(
        self,
        tmp_path: Path,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[
                _scan(repo_id, path="/api/x"),
                _scan(repo_id, path="/api/y"),
            ],
        )
        paths = ProjectPaths(tmp_path / "proj")
        seeds_path, oas3_path = service.regenerate_artifacts(
            repo_id=repo_id,
            project_paths=paths,
            repo_dir_key="my-uuid",
        )
        assert Path(seeds_path).exists()
        assert Path(oas3_path).exists()
        seeds = Path(seeds_path).read_text(encoding="utf-8")
        assert "/api/x" in seeds
        assert "/api/y" in seeds
        doc = json.loads(Path(oas3_path).read_text(encoding="utf-8"))
        assert "/api/x" in doc["paths"]

    def test_empty_repo_writes_empty_artifacts(
        self,
        tmp_path: Path,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        paths = ProjectPaths(tmp_path / "proj")
        seeds_path, oas3_path = service.regenerate_artifacts(
            repo_id=repo_id,
            project_paths=paths,
            repo_dir_key="empty",
        )
        assert Path(seeds_path).read_text(encoding="utf-8") == ""
        doc = json.loads(Path(oas3_path).read_text(encoding="utf-8"))
        assert doc["paths"] == {}


class TestCleanup:
    def test_delete_for_repo(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
        repo_id: int,
    ) -> None:
        service.ingest_scan_source(
            repo_id=repo_id,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(repo_id, path="/a"), _scan(repo_id, path="/b")],
        )
        n = service.delete_for_repo(repo_id)
        assert n == 2
        repo = UrlFindingRepository(factory)
        assert repo.list_for_repo(repo_id) == []

    def test_delete_all(
        self,
        factory: ConnectionFactory,
        service: UrlInventoryService,
    ) -> None:
        rr = RepositoryRepository(factory)
        rid_a = rr.insert(_repo("a"))
        rid_b = rr.insert(_repo("b"))
        service.ingest_scan_source(
            repo_id=rid_a,
            run_id=None,
            tool=UrlTool.KATANA,
            entries=[_scan(rid_a, path="/x")],
        )
        service.ingest_scan_source(
            repo_id=rid_b,
            run_id=None,
            tool=UrlTool.NOIR,
            entries=[_scan(rid_b, path="/y", tool=UrlTool.NOIR)],
        )
        n = service.delete_all()
        assert n == 2
        repo = UrlFindingRepository(factory)
        assert repo.list_for_repo(rid_a) == []
        assert repo.list_for_repo(rid_b) == []
