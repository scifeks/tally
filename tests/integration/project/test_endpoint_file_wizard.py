"""Integration tests for endpoint file handling in add_repository().

Covers:
- add_repository() with convert_endpoint_file mocked to succeed:
  repo.oas3_path is set to the converted path
- add_repository() with convert_endpoint_file raising ConverterError:
  repo.oas3_path is empty; repository is still saved
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


class TestEndpointFileWizard:
    def test_add_repository_endpoint_file_success(self, tmp_path: Path) -> None:
        """convert_endpoint_file succeeds — repo.oas3_path is set."""
        from application.project.wizard import InteractiveProjectWizard

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_src = tmp_path / "api.json"
        oas3_src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}'
        )
        converted = tmp_path / "endpoints" / "api.json"

        pm = _setup_project(tmp_path / "pm")
        wizard = InteractiveProjectWizard(pm)

        # name, type, mode, path, langs, deps_file, base_urls,
        # test_dirs, ignore_dirs, endpoint_file
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
        ]
        with (
            patch("builtins.input", side_effect=inputs),
            patch(
                "infrastructure.endpoints.converters.convert_endpoint_file",
                return_value=converted,
            ),
        ):
            repo = wizard.add_repository("test-project")

        assert repo is not None
        assert repo.oas3_path == str(converted)

    def test_add_repository_endpoint_file_converter_error(self, tmp_path: Path) -> None:
        """ConverterError — repo.oas3_path is empty, repo is still saved."""
        from application.project.wizard import InteractiveProjectWizard
        from infrastructure.endpoints.converters.base import ConverterError

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_src = tmp_path / "api.json"
        oas3_src.write_text(
            '{"openapi": "3.0.0", "info": {"title": "t", "version": "1"}, "paths": {}}'
        )

        pm = _setup_project(tmp_path / "pm")
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
        ]
        with (
            patch("builtins.input", side_effect=inputs),
            patch(
                "infrastructure.endpoints.converters.convert_endpoint_file",
                side_effect=ConverterError("conversion failed"),
            ),
        ):
            repo = wizard.add_repository("test-project")

        assert repo is not None
        assert repo.oas3_path == ""
        repos = pm.config.load_repositories("test-project")
        assert any(r.name == "my-repo" for r in repos)
