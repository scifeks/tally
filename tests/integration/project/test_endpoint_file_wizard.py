"""Integration tests for endpoint file handling in ``add_repository``.

Phase 9: the wizard no longer stores a converted OAS3 path on the
``Repository`` model. It copies the user upload into
``endpoints/<repo.uuid>/user_uploads/`` and ingests the contents into
``url_findings`` via ``UserFileProvider`` + ``UrlInventoryService``.
These tests exercise both branches:

- happy path → ``url_findings`` rows are inserted
- conversion failure → repo is still saved; no ``url_findings`` rows
"""

from __future__ import annotations

import datetime
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_pm(base_path: Path):  # type: ignore[no-untyped-def]
    import sys

    if str(_TALLY_ROOT) not in sys.path:
        sys.path.insert(0, str(_TALLY_ROOT))
    from application.project import ProjectManager

    _write_global_config(base_path)
    return ProjectManager(base_path=str(base_path))


def _setup_project(base_path: Path):  # type: ignore[no-untyped-def]
    from core.config.schemas import ProjectConfig

    pm = _make_pm(base_path)
    pm.create_project_dirs("test-project")
    pc = ProjectConfig(
        project_name="test-project",
        created=datetime.datetime.now().isoformat(),
        repositories=[],
    )
    pm.config.save_project_config("test-project", pc)
    return pm


def _count_url_findings(base_path: Path, repo_uuid: str) -> int:
    from core.project_paths import ProjectPaths
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.repositories import RepositoryRepository
    from infrastructure.store.repositories.url_findings import UrlFindingRepository

    paths = ProjectPaths.from_canonical(base_path, "test-project")
    if not paths.findings_db.exists():
        return 0
    factory = ConnectionFactory(paths.findings_db)
    repo_row = RepositoryRepository(factory).get_by_uuid(repo_uuid)
    if repo_row is None:
        return 0
    return len(UrlFindingRepository(factory).list_for_repo(repo_row.id))


class TestEndpointFileWizard:
    def test_add_repository_endpoint_file_success(self, tmp_path: Path) -> None:
        """User-uploaded OAS3 → file copied + ``url_findings`` rows inserted."""
        from application.project.wizard import InteractiveProjectWizard
        from core.project_paths import ProjectPaths

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_src = tmp_path / "api.json"
        oas3_src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"},'
            ' "paths": {"/users": {"get":'
            ' {"responses": {"200": {"description": ""}}}}}}'
        )

        base_path = tmp_path / "pm"
        pm = _setup_project(base_path)
        wizard = InteractiveProjectWizard(pm)

        inputs = [
            "my-repo",
            "api",
            "local",
            str(repo_dir),
            "python",
            "",
            "",
            "",
            "",
            str(oas3_src),
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard.add_repository("test-project")

        assert repo is not None
        assert repo.uuid

        # The wizard copies the upload under endpoints/<uuid>/user_uploads/.
        paths = ProjectPaths.from_canonical(base_path, "test-project")
        upload = paths.endpoint_dir(repo.uuid) / "user_uploads" / "api.json"
        assert upload.exists()

        # And ingests its contents into url_findings.
        assert _count_url_findings(base_path, repo.uuid) == 1

    def test_add_repository_endpoint_file_converter_error(self, tmp_path: Path) -> None:
        """``ConverterError`` → repo still saved; no ``url_findings`` rows."""
        from application.project.wizard import InteractiveProjectWizard
        from infrastructure.endpoints.converters.base import ConverterError

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_src = tmp_path / "api.json"
        oas3_src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}'
        )

        base_path = tmp_path / "pm"
        pm = _setup_project(base_path)
        wizard = InteractiveProjectWizard(pm)

        inputs = [
            "my-repo",
            "api",
            "local",
            str(repo_dir),
            "python",
            "",
            "",
            "",
            "",
            str(oas3_src),
            "",  # auth
        ]
        with (
            patch("builtins.input", side_effect=inputs),
            patch(
                "infrastructure.endpoints.converters.service.convert_endpoint_file",
                side_effect=ConverterError("conversion failed"),
            ),
        ):
            repo = wizard.add_repository("test-project")

        assert repo is not None
        assert repo.uuid
        repos = pm.config.load_repositories("test-project")
        assert any(r.name == "my-repo" for r in repos)
        assert _count_url_findings(base_path, repo.uuid) == 0
