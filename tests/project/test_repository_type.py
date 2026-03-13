"""Tests for repository type validation in schemas and manager helpers."""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas import ProjectConfig, Repository  # noqa: E402
from core.project.manager import (  # noqa: E402
    ProjectManager,
    _parse_repo_types,
    _validate_repo_types,
)


def _write_global_config(base_path: Path) -> None:
    """Write a minimal global.json so ConfigManager initialises without error."""
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "base_url": "http://localhost:11434",
                    "model": "test",
                },
                "ollama_embedding": {
                    "base_url": "http://localhost:11434",
                    "model": "nomic-embed-text:latest",
                },
            }
        )
    )


def _make_pm(base_path: Path) -> ProjectManager:
    _write_global_config(base_path)
    return ProjectManager(base_path=str(base_path))


# ---------------------------------------------------------------------------
# _parse_repo_types
# ---------------------------------------------------------------------------


class TestParseRepoTypes:
    def test_single_type(self) -> None:
        assert _parse_repo_types("api") == ["api"]

    def test_multiple_types(self) -> None:
        assert _parse_repo_types("api,ui") == ["api", "ui"]

    def test_strips_spaces(self) -> None:
        assert _parse_repo_types("api, ui") == ["api", "ui"]

    def test_leading_trailing_spaces(self) -> None:
        assert _parse_repo_types(" ui ") == ["ui"]

    def test_empty_string_returns_empty(self) -> None:
        assert _parse_repo_types("") == []

    def test_only_commas_returns_empty(self) -> None:
        assert _parse_repo_types(",,,") == []

    def test_library_single(self) -> None:
        assert _parse_repo_types("library") == ["library"]


# ---------------------------------------------------------------------------
# _validate_repo_types
# ---------------------------------------------------------------------------


class TestValidateRepoTypes:
    def test_valid_api(self) -> None:
        assert _validate_repo_types(["api"]) is None

    def test_valid_ui(self) -> None:
        assert _validate_repo_types(["ui"]) is None

    def test_valid_library(self) -> None:
        assert _validate_repo_types(["library"]) is None

    def test_valid_api_ui(self) -> None:
        assert _validate_repo_types(["api", "ui"]) is None

    def test_valid_ui_api(self) -> None:
        assert _validate_repo_types(["ui", "api"]) is None

    def test_empty_returns_error(self) -> None:
        result = _validate_repo_types([])
        assert result is not None
        assert "required" in result.lower()

    def test_invalid_type_returns_error(self) -> None:
        result = _validate_repo_types(["backend"])
        assert result is not None
        assert "backend" in result

    def test_library_with_api_returns_error(self) -> None:
        result = _validate_repo_types(["library", "api"])
        assert result is not None
        assert "library" in result.lower()
        assert "exclusive" in result.lower() or "cannot" in result.lower()

    def test_library_with_ui_returns_error(self) -> None:
        result = _validate_repo_types(["library", "ui"])
        assert result is not None
        assert "library" in result.lower()

    def test_library_with_api_and_ui_returns_error(self) -> None:
        result = _validate_repo_types(["library", "api", "ui"])
        assert result is not None


# ---------------------------------------------------------------------------
# Repository schema validation
# ---------------------------------------------------------------------------


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "type": ["api"],
        "path": str(_TALLY_ROOT),
        "languages": ["python"],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


class TestRepositoryTypeSchema:
    def test_valid_api(self) -> None:
        repo = _make_repo(type=["api"])
        assert repo.type == ["api"]

    def test_valid_ui(self) -> None:
        repo = _make_repo(type=["ui"])
        assert repo.type == ["ui"]

    def test_valid_library(self) -> None:
        repo = _make_repo(type=["library"])
        assert repo.type == ["library"]

    def test_valid_api_ui(self) -> None:
        repo = _make_repo(type=["api", "ui"])
        assert repo.type == ["api", "ui"]

    def test_missing_type_raises(self) -> None:
        with pytest.raises(Exception):
            Repository(  # type: ignore[call-arg]
                name="r",
                path=str(_TALLY_ROOT),
                languages=[],
            )

    def test_empty_type_raises(self) -> None:
        with pytest.raises(Exception):
            _make_repo(type=[])

    def test_invalid_type_raises(self) -> None:
        with pytest.raises(Exception, match="Invalid"):
            _make_repo(type=["backend"])

    def test_library_with_api_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "api"])

    def test_library_with_ui_raises(self) -> None:
        with pytest.raises(Exception, match="library"):
            _make_repo(type=["library", "ui"])

    def test_no_paths_raises(self) -> None:
        with pytest.raises(Exception, match="path"):
            _make_repo(path="", docker_path="")

    def test_docker_only_repo_valid(self) -> None:
        # Existing docker-only repos (no local path) must still load without error
        repo = _make_repo(path="", docker_path="/mnt/repo", container_name="c")
        assert repo.docker_path == "/mnt/repo"
        assert repo.path == ""

    def test_docker_path_requires_container_name(self) -> None:
        with pytest.raises(Exception, match="container_name"):
            _make_repo(docker_path="/mnt/repo", container_name="")

    def test_valid_docker_repo(self) -> None:
        repo = _make_repo(docker_path="/mnt/repo", container_name="my-container")
        assert repo.docker_path == "/mnt/repo"
        assert repo.container_name == "my-container"

    def test_valid_local_repo(self) -> None:
        repo = _make_repo()
        assert repo.path == str(_TALLY_ROOT)
        assert repo.docker_path == ""


# ---------------------------------------------------------------------------
# _interview_single_repo
# ---------------------------------------------------------------------------


class TestInterviewSingleRepo:
    def test_add_local_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        inputs = ["my-repo", "api", "local", str(repo_dir), "python", ""]
        with patch("builtins.input", side_effect=inputs):
            repo = pm._interview_single_repo(1)
        assert repo is not None
        assert repo.path == str(repo_dir)
        assert repo.docker_path == ""
        assert repo.container_name == ""

    def test_add_docker_repo(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        inputs = [
            "my-repo",
            "api",
            "docker",
            "my-container",
            "/mnt/repo",
            str(repo_dir),
            "python",
            "",
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = pm._interview_single_repo(1)
        assert repo is not None
        assert repo.docker_path == "/mnt/repo"
        assert repo.container_name == "my-container"
        assert repo.path == str(repo_dir)

    def test_add_invalid_mode_then_valid(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        inputs = ["my-repo", "api", "nope", "local", str(repo_dir), "python", ""]
        with patch("builtins.input", side_effect=inputs):
            repo = pm._interview_single_repo(1)
        assert repo is not None
        assert repo.docker_path == ""

    def test_add_nonexistent_path_retries(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        pm = _make_pm(tmp_path / "pm")
        inputs = [
            "my-repo",
            "api",
            "local",
            "/no/such/path",
            str(repo_dir),
            "python",
            "",
        ]
        with patch("builtins.input", side_effect=inputs):
            repo = pm._interview_single_repo(1)
        assert repo is not None
        assert repo.path == str(repo_dir)


# ---------------------------------------------------------------------------
# edit_repository
# ---------------------------------------------------------------------------


class TestEditRepository:
    def _setup_project(self, base_path: Path, repo: Repository) -> ProjectManager:
        pm = _make_pm(base_path)
        pm._create_project_dirs("test-project")
        pc = ProjectConfig(
            project_name="test-project",
            created=datetime.datetime.now().isoformat(),
            repositories=[repo],
        )
        pm.config.save_project_config("test-project", pc)
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
        # Switch from docker to local; keep all other defaults
        inputs = ["", "", "local", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            updated = pm.edit_repository("test-project", "my-repo")
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
        inputs = ["", "", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            updated = pm.edit_repository("test-project", "my-repo")
        assert updated is not None
        assert updated.path == str(repo_dir)
        assert updated.docker_path == ""
