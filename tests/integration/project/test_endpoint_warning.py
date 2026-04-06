"""Tests that the ZAP accuracy warning is printed at the endpoint file prompts.

Covers:
- _interview_single_repo: warning always shown before the endpoint prompt
- edit_repository, no existing oas3_path: warning shown before the prompt
- edit_repository, existing oas3_path, user replaces: warning shown
- edit_repository, existing oas3_path, user keeps: warning NOT shown
"""

from __future__ import annotations

import datetime
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
from core.config.schemas import ProjectConfig, Repository  # noqa: E402

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
        pm.create_project_dirs("test-project")
        pm.config.save_project_config(
            "test-project",
            ProjectConfig(
                project_name="test-project",
                created=datetime.datetime.now().isoformat(),
                repositories=[repo],
            ),
        )
        # press Enter for everything (no endpoint file provided)
        inputs = ["", "", "", "", "", "", "", "", "", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING in out

    def test_warning_shown_in_edit_when_replacing_existing_oas3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning shown when user chooses to replace an existing endpoint file."""
        fake_oas3 = tmp_path / "api.json"
        fake_oas3.write_text("{}")
        repo = _make_repo(name="my-repo", path=str(tmp_path), oas3_path=str(fake_oas3))
        pm = _make_pm(tmp_path / "pm")
        pm.create_project_dirs("test-project")
        pm.config.save_project_config(
            "test-project",
            ProjectConfig(
                project_name="test-project",
                created=datetime.datetime.now().isoformat(),
                repositories=[repo],
            ),
        )
        # name, type, mode, path, langs, deps, urls, test_dirs, ignore_dirs,
        # "y" to replace, then Enter to leave new path empty
        inputs = ["", "", "", "", "", "", "", "", "", "y", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING in out

    def test_warning_not_shown_in_edit_when_keeping_existing_oas3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Warning NOT shown when user keeps the existing endpoint file."""
        fake_oas3 = tmp_path / "api.json"
        fake_oas3.write_text("{}")
        repo = _make_repo(name="my-repo", path=str(tmp_path), oas3_path=str(fake_oas3))
        pm = _make_pm(tmp_path / "pm")
        pm.create_project_dirs("test-project")
        pm.config.save_project_config(
            "test-project",
            ProjectConfig(
                project_name="test-project",
                created=datetime.datetime.now().isoformat(),
                repositories=[repo],
            ),
        )
        # name, type, mode, path, langs, deps, urls, test_dirs, ignore_dirs, "n"
        inputs = ["", "", "", "", "", "", "", "", "", "n"]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING not in out
