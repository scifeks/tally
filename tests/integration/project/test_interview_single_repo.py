"""Tests for InteractiveProjectWizard._interview_single_repo."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager  # noqa: E402
from application.project.wizard import InteractiveProjectWizard  # noqa: E402

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


class TestInterviewSingleRepo:
    def test_add_local_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        # inputs: name, type, mode, path, languages, dependencies_file, base_urls,
        #         test_dirs, ignore_dirs, endpoint_file, auth
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
            "",
            "",
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.path == str(repo_dir)
        assert repo.docker_path == ""
        assert repo.container_name == ""

    def test_add_docker_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        inputs = [
            "my-repo",
            "api",
            "docker",
            "my-container",
            "/mnt/repo",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "",
            "",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.docker_path == "/mnt/repo"
        assert repo.container_name == "my-container"
        assert repo.path == str(repo_dir)

    def test_add_invalid_mode_then_valid(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        inputs = [
            "my-repo",
            "api",
            "nope",
            "local",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "",
            "",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.docker_path == ""

    def test_add_nonexistent_path_retries(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        inputs = [
            "my-repo",
            "api",
            "local",
            "/no/such/path",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "",
            "",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.path == str(repo_dir)

    def test_auto_detected_test_dirs_accepted(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        # "" for dependencies_file; "" accepts defaults; "" for endpoint
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
            "",
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.test_dirs == ["tests"]
        assert repo.ignore_dirs == []

    def test_test_dirs_overridden_by_user(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        # user overrides detected "tests" with "spec, e2e"; ignore_dirs empty
        inputs = [
            "my-repo",
            "api",
            "local",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "spec, e2e",
            "",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.test_dirs == ["spec", "e2e"]
        assert repo.ignore_dirs == []

    def test_no_test_dirs_empty_input(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
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
            "",
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.test_dirs == []

    def test_ignore_dirs_captured(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        # no test dirs; ignore_dirs = vendor, node_modules
        inputs = [
            "my-repo",
            "api",
            "local",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "",
            "vendor, node_modules",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.ignore_dirs == ["vendor", "node_modules"]

    def test_both_test_and_ignore_dirs(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        pm = _make_pm(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)
        inputs = [
            "my-repo",
            "api",
            "local",
            str(repo_dir),
            "python",
            "",  # dependencies_file
            "",
            "tests",
            "vendor, mocks",
            "",  # endpoint file
            "",  # auth
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = wizard._interview_single_repo(1)
        assert repo is not None
        assert repo.test_dirs == ["tests"]
        assert repo.ignore_dirs == ["vendor", "mocks"]
