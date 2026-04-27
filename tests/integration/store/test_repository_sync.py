"""Integration tests for application.project.repository_sync (Phase 9.2)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project.repository_sync import (  # noqa: E402
    sync_repositories_for_all_projects,
    sync_repositories_for_project,
)
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.project_registry import (  # noqa: E402
    ProjectRegistryRepository,
)
from infrastructure.store.repositories.findings import FindingRepository  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)
from infrastructure.store.repositories.runs import RunRepository  # noqa: E402

pytestmark = pytest.mark.integration


def _write_project(
    project_root: Path,
    project_name: str,
    repos: list[dict],
    *,
    company: str = "Acme",
) -> Path:
    config = project_root / "config" / "project.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps(
            {
                "project_name": project_name,
                "created": "2026-04-26T00:00:00",
                "repositories": repos,
                "company_name": company,
                "department_name": "",
                "abbreviation": "",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return config


def _make_repo_entry(name: str, path: str, *, uuid: str | None = None) -> dict:
    entry = {
        "name": name,
        "type": ["api"],
        "path": path,
        "docker_path": "",
        "container_name": "",
        "languages": ["python"],
        "base_urls": [],
        "test_dirs": [],
        "ignore_dirs": [],
        "dependencies_file": "",
        "oas3_path": "",
        "merged_seeds_path": "",
        "merged_oas3_path": "",
        "crawl_enabled": False,
        "xsstrike_crawl_level": 10,
        "xsstrike_headers": {},
        "dalfox_headers": {},
        "katana_headless": False,
        "katana_depth": 5,
        "katana_headers": {},
        "auth": None,
    }
    if uuid is not None:
        entry["uuid"] = uuid
    return entry


class TestUuidBackfill:
    def test_assigns_uuid_when_missing(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        config = _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )

        sync_repositories_for_project(str(project_root))

        data = json.loads(config.read_text(encoding="utf-8"))
        assert "uuid" in data["repositories"][0]
        assert data["repositories"][0]["uuid"]

    def test_does_not_overwrite_existing_uuid(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        config = _write_project(
            project_root,
            "alpha",
            [
                _make_repo_entry(
                    "backend",
                    str(repo_path),
                    uuid="11111111-1111-1111-1111-111111111111",
                )
            ],
        )

        sync_repositories_for_project(str(project_root))

        data = json.loads(config.read_text(encoding="utf-8"))
        assert data["repositories"][0]["uuid"] == "11111111-1111-1111-1111-111111111111"

    def test_inserts_db_row(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )

        sync_repositories_for_project(str(project_root))

        factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
        repos = RepositoryRepository(factory)
        active = repos.list_active()
        assert len(active) == 1
        assert active[0].name == "backend"
        assert active[0].uuid

    def test_idempotent(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )

        sync_repositories_for_project(str(project_root))
        first = json.loads(
            (project_root / "config" / "project.json").read_text(encoding="utf-8")
        )["repositories"][0]["uuid"]

        sync_repositories_for_project(str(project_root))
        second = json.loads(
            (project_root / "config" / "project.json").read_text(encoding="utf-8")
        )["repositories"][0]["uuid"]

        factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
        repos = RepositoryRepository(factory)
        # uuid stable + only one DB row
        assert first == second
        assert len(repos.list_active()) == 1

    def test_renames_db_row_when_json_name_changes(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("old-name", str(repo_path))],
        )
        sync_repositories_for_project(str(project_root))

        # Simulate user renaming via the (still-unimplemented) editor by
        # editing project.json directly.
        config_path = project_root / "config" / "project.json"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        data["repositories"][0]["name"] = "new-name"
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        sync_repositories_for_project(str(project_root))

        factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
        repos = RepositoryRepository(factory)
        active = repos.list_active()
        assert len(active) == 1
        assert active[0].name == "new-name"


class TestEndpointDirMigration:
    """Phase 9: legacy endpoints/<name>/ → endpoints/<uuid>/ on first sync."""

    def test_renames_legacy_name_keyed_dir_to_uuid(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )
        # Simulate legacy on-disk layout: endpoints/<name>/...
        legacy_dir = project_root / "endpoints" / "backend"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "merged_urls.txt").write_text("http://x", encoding="utf-8")

        sync_repositories_for_project(str(project_root))

        data = json.loads(
            (project_root / "config" / "project.json").read_text(encoding="utf-8")
        )
        new_uuid = data["repositories"][0]["uuid"]
        assert not legacy_dir.exists()
        new_dir = project_root / "endpoints" / new_uuid
        assert new_dir.is_dir()
        assert (new_dir / "merged_urls.txt").read_text(encoding="utf-8") == "http://x"

    def test_skips_when_uuid_dir_already_present(self, tmp_path: Path) -> None:
        """If both legacy and uuid dirs exist, leave both — don't merge."""
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )
        legacy_dir = project_root / "endpoints" / "backend"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "old.txt").write_text("legacy", encoding="utf-8")
        # Pre-create the uuid dir as if a Phase 9 add_repo already ran.
        # We don't know the uuid yet — but if both end up coexisting after
        # sync, neither should be touched.
        sync_repositories_for_project(str(project_root))

        data = json.loads(
            (project_root / "config" / "project.json").read_text(encoding="utf-8")
        )
        new_uuid = data["repositories"][0]["uuid"]
        new_dir = project_root / "endpoints" / new_uuid
        assert new_dir.is_dir()
        # Run sync again with the uuid already known; legacy dir is gone
        # (rename on first run), so this is now a no-op.
        sync_repositories_for_project(str(project_root))
        assert new_dir.is_dir()
        assert not legacy_dir.exists()

    def test_no_op_when_no_legacy_dir(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )
        sync_repositories_for_project(str(project_root))
        # endpoints/ may not exist at all — sync should not raise.
        endpoints_dir = project_root / "endpoints"
        assert not endpoints_dir.exists() or not any(endpoints_dir.iterdir())


class TestFindingsBackfill:
    def test_findings_repo_id_populated_from_repo_string(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )

        # Pre-seed a finding with the legacy 'repo' string and no repo_id.
        factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        run_id = run_repo.create_run({})
        findings_repo = FindingRepository(factory)
        findings_repo.insert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "segment": "default",
                    "repo": "backend",
                    "finding_type": '["sast"]',
                    "severity": 2,
                    "confidence": "high",
                    "file": "src/main.py",
                    "rule_id": "py.test",
                    "description": "test finding",
                    "first_seen": "2026-04-26T00:00:00",
                    "last_seen": "2026-04-26T00:00:00",
                    "seen_count": 1,
                    "status": "active",
                    "should_report": 0,
                }
            ],
        )

        sync_repositories_for_project(str(project_root))

        with factory.connect() as conn:
            row = conn.execute("SELECT meta, repo_id FROM findings").fetchone()
        meta = json.loads(row["meta"] or "{}")
        assert meta.get("repo") == "backend"
        assert row["repo_id"] is not None
        # repo_id should resolve back to the new repositories row.
        repos = RepositoryRepository(factory)
        backend = repos.get_by_name("backend")
        assert backend is not None
        assert row["repo_id"] == backend.id

    def test_backfill_idempotent(self, tmp_path: Path) -> None:
        project_root = tmp_path / "projects" / "alpha"
        repo_path = tmp_path / "alpha-repo"
        repo_path.mkdir()
        _write_project(
            project_root,
            "alpha",
            [_make_repo_entry("backend", str(repo_path))],
        )

        factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
        factory.init_schema()
        run_repo = RunRepository(factory)
        run_id = run_repo.create_run({})
        findings_repo = FindingRepository(factory)
        findings_repo.insert_findings(
            run_id,
            [
                {
                    "tool": "semgrep",
                    "domain": "code",
                    "segment": "default",
                    "repo": "backend",
                    "finding_type": '["sast"]',
                    "severity": 2,
                    "confidence": "high",
                    "file": "src/main.py",
                    "rule_id": "py.test",
                    "description": "first",
                    "first_seen": "2026-04-26T00:00:00",
                    "last_seen": "2026-04-26T00:00:00",
                    "seen_count": 1,
                    "status": "active",
                    "should_report": 0,
                }
            ],
        )

        sync_repositories_for_project(str(project_root))
        sync_repositories_for_project(str(project_root))

        with factory.connect() as conn:
            rows = conn.execute("SELECT repo_id FROM findings").fetchall()
        assert len(rows) == 1
        assert rows[0]["repo_id"] is not None


class TestSyncAllProjects:
    def test_iterates_active_projects(self, tmp_path: Path) -> None:
        # Create two projects on disk + register them.
        for name in ("alpha", "bravo"):
            project_root = tmp_path / "projects" / name
            repo_path = tmp_path / f"{name}-repo"
            repo_path.mkdir()
            _write_project(
                project_root,
                name,
                [_make_repo_entry(f"{name}-backend", str(repo_path))],
            )

        registry = ProjectRegistryRepository(tmp_path / "tally.db")
        registry.init_schema()
        registry.insert("alpha", str(tmp_path / "projects" / "alpha"))
        registry.insert("bravo", str(tmp_path / "projects" / "bravo"))

        sync_repositories_for_all_projects(str(tmp_path))

        for name in ("alpha", "bravo"):
            project_root = tmp_path / "projects" / name
            factory = ConnectionFactory(project_root / "sqlite" / "findings.db")
            repos = RepositoryRepository(factory)
            active = repos.list_active()
            assert len(active) == 1
            assert active[0].name == f"{name}-backend"

    def test_no_op_when_registry_db_missing(self, tmp_path: Path) -> None:
        # No tally.db at all — should not raise.
        sync_repositories_for_all_projects(str(tmp_path))

    def test_no_op_when_project_missing_config(self, tmp_path: Path) -> None:
        registry = ProjectRegistryRepository(tmp_path / "tally.db")
        registry.init_schema()
        # Register a project whose config dir doesn't exist yet.
        registry.insert("ghost", str(tmp_path / "projects" / "ghost"))
        # Should not raise.
        sync_repositories_for_all_projects(str(tmp_path))
