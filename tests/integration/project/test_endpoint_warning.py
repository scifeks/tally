"""Tests that the ZAP accuracy warning is printed at the endpoint file prompts.

Covers:
- ``_interview_single_repo``: warning always shown before the endpoint prompt
- ``edit_repository``, no existing endpoint file: warning shown
- ``edit_repository``, existing endpoint file, user replaces: warning shown
- ``edit_repository``, existing endpoint file, user keeps: warning NOT shown

"existing endpoint file" is detected via the repo's ``url_seed_file``
DB column.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import (  # noqa: E402
    ProjectManager,
    ProjectRepositoriesService,
)
from application.project.wizard import InteractiveProjectWizard  # noqa: E402
from core.config.schemas import Repository  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402

pytestmark = pytest.mark.integration

_WARNING = (
    "Warning: when an endpoint file is configured, Noir"
    " is skipped and ZAP relies entirely on that file."
    " ZAP results will be less accurate if the file is"
    " incomplete."
)


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_pm(base_path: Path) -> ProjectManager:
    from infrastructure.store.connection import ConnectionFactory

    _write_global_config(base_path)

    def schema_init(db_path):
        ConnectionFactory(db_path).init_schema()

    return ProjectManager(base_path=str(base_path), schema_initializer=schema_init)


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "path": str(_TALLY_ROOT),
        "services": [
            {
                "name": "default",
                "type": ["api"],
                "languages": ["python"],
            }
        ],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


def _setup_project_with_repo(
    pm: ProjectManager, repo: Repository
) -> tuple[int, Repository]:
    pm.create_project_dirs("test-project")
    pm.save_project("test-project")
    row = pm.registry.resolve_by_name("test-project")
    assert row is not None
    project_id = row.id
    service = ProjectRepositoriesService(pm.registry, pm.config)
    persisted = service.create(project_id, repo)
    return project_id, persisted


def _seed_existing_upload(
    pm: ProjectManager, project_id: int, repo: Repository
) -> None:
    """Drop a stub upload + record its path so the wizard treats *repo* as
    already having an endpoint file."""
    paths = ProjectPaths.from_canonical(pm.base_path, "test-project")
    epoch = int(time.time())
    upload_dir = paths.seed_upload_dir(repo.name, epoch)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / "api.json"
    target.write_text("{}", encoding="utf-8")
    assert repo.id is not None
    service = ProjectRepositoriesService(pm.registry, pm.config)
    service.record_seed_file(project_id, repo.id, str(target))


class TestEndpointWarning:
    def test_warning_shown_in_interview_single_repo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning is printed before the endpoint file prompt in repo add."""
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        inputs = [
            "my-repo",
            "api",
            "local",
            str(tmp_path),
            "python",
            "",
            "",
            "",
            "",
            "",
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            wizard._interview_single_repo(1)
        out = capsys.readouterr().out
        assert _WARNING in out

    def test_warning_shown_in_edit_when_no_existing_oas3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning shown when editing a repo that has no current endpoint file."""
        repo = _make_repo(name="my-repo", path=str(tmp_path))
        pm = _make_pm(tmp_path / "pm")
        _setup_project_with_repo(pm, repo)
        # press Enter for everything (no endpoint file provided)
        inputs = ["", "", "", "", "", "", "", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING in out

    def test_warning_shown_in_edit_when_replacing_existing_oas3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning shown when user chooses to replace an existing endpoint file."""
        repo = _make_repo(name="my-repo", path=str(tmp_path))
        pm = _make_pm(tmp_path / "pm")
        project_id, persisted = _setup_project_with_repo(pm, repo)
        _seed_existing_upload(pm, project_id, persisted)
        # name, type, mode, path, langs, deps, urls, test_dirs, ignore_dirs,
        # "y" to replace, then Enter to leave new path empty, then auth
        inputs = ["", "", "", "", "", "", "", "", "", "y", "", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING in out

    def test_warning_not_shown_in_edit_when_keeping_existing_oas3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning NOT shown when user keeps the existing endpoint file."""
        repo = _make_repo(name="my-repo", path=str(tmp_path))
        pm = _make_pm(tmp_path / "pm")
        project_id, persisted = _setup_project_with_repo(pm, repo)
        _seed_existing_upload(pm, project_id, persisted)
        # name, type, mode, path, langs, deps, urls, test_dirs, ignore_dirs, "n", auth
        inputs = ["", "", "", "", "", "", "", "", "", "n", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING not in out
