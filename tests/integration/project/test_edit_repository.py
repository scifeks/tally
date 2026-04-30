"""Tests for InteractiveProjectWizard.edit_repository."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager, ProjectRepositoriesService  # noqa: E402
from application.project.wizard import InteractiveProjectWizard  # noqa: E402
from core.config.schemas import Repository  # noqa: E402

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    """Copy real global.json into the test tmp_path; skip if absent."""
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _make_pm(base_path: Path) -> ProjectManager:
    _write_global_config(base_path)
    return ProjectManager(base_path=str(base_path))


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "type": ["api"],
        "path": str(_TALLY_ROOT),
        "languages": ["python"],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


class TestEditRepository:
    def _setup_project(self, base_path: Path, repo: Repository) -> ProjectManager:
        pm = _make_pm(base_path)
        pm.create_project_dirs("test-project")
        pm.save_project("test-project")
        row = pm.registry.resolve_by_name("test-project")
        assert row is not None
        service = ProjectRepositoriesService(pm.registry, pm.config)
        service.create(int(row["id"]), repo)
        return pm

    def test_edit_docker_to_local(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(
            name="my-repo",
            path=str(repo_dir),
            docker_path="/mnt/repo",
            container_name="my-container",
        )
        pm = self._setup_project(tmp_path / "pm", repo)
        # Switch from docker to local; "" for deps file; "" for endpoint file; "" auth
        inputs = ["", "", "local", "", "", "", "", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            updated = InteractiveProjectWizard(pm).edit_repository(
                "test-project", "my-repo"
            )
        assert updated is not None
        assert updated.docker_path == ""
        assert updated.container_name == ""
        assert updated.path == str(repo_dir)

    def test_edit_local_keeps_defaults(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(name="my-repo", path=str(repo_dir))
        pm = self._setup_project(tmp_path / "pm", repo)
        # Press Enter for everything — keep existing values
        # (extra "" for endpoint file prompt, then auth)
        inputs = ["", "", "", "", "", "", "", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            updated = InteractiveProjectWizard(pm).edit_repository(
                "test-project", "my-repo"
            )
        assert updated is not None
        assert updated.path == str(repo_dir)
        assert updated.docker_path == ""
