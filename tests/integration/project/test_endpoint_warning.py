"""Tests that the ZAP accuracy warning is printed at the endpoint file prompts.

Covers:
- ``_interview_single_repo``: warning always shown before the endpoint prompt
- ``edit_repository``, no existing endpoint file: warning shown
- ``edit_repository``, existing endpoint file, user replaces: warning shown
- ``edit_repository``, existing endpoint file, user keeps: warning NOT shown

Phase 9: "existing endpoint file" is detected by the presence of any
file under ``endpoints/<repo.uuid>/user_uploads/`` (not by reading
``Repository.oas3_path``, which no longer exists).
"""

from __future__ import annotations

import datetime
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.project import ProjectManager  # noqa: E402
from application.project.wizard import InteractiveProjectWizard  # noqa: E402
from core.config.schemas import ProjectConfig, Repository  # noqa: E402
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
    _write_global_config(base_path)
    return ProjectManager(base_path=str(base_path))


def _make_repo(**kwargs: object) -> Repository:
    defaults: dict[str, object] = {
        "name": "test-repo",
        "uuid": str(uuid4()),
        "type": ["api"],
        "path": str(_TALLY_ROOT),
        "languages": ["python"],
    }
    defaults.update(kwargs)
    return Repository(**defaults)  # type: ignore[arg-type]


def _seed_existing_upload(pm_base: Path, project_name: str, repo: Repository) -> None:
    """Drop a stub file under ``endpoints/<uuid>/user_uploads/`` so the wizard
    treats *repo* as already having an endpoint file."""
    paths = ProjectPaths.from_canonical(pm_base, project_name)
    upload_dir = paths.endpoint_dir(repo.uuid) / "user_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / "api.json").write_text("{}", encoding="utf-8")


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
        pm_base = tmp_path / "pm"
        pm = _make_pm(pm_base)
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
        pm_base = tmp_path / "pm"
        pm = _make_pm(pm_base)
        pm.create_project_dirs("test-project")
        pm.config.save_project_config(
            "test-project",
            ProjectConfig(
                project_name="test-project",
                created=datetime.datetime.now().isoformat(),
                repositories=[repo],
            ),
        )
        _seed_existing_upload(pm_base, "test-project", repo)
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
        pm_base = tmp_path / "pm"
        pm = _make_pm(pm_base)
        pm.create_project_dirs("test-project")
        pm.config.save_project_config(
            "test-project",
            ProjectConfig(
                project_name="test-project",
                created=datetime.datetime.now().isoformat(),
                repositories=[repo],
            ),
        )
        _seed_existing_upload(pm_base, "test-project", repo)
        # name, type, mode, path, langs, deps, urls, test_dirs, ignore_dirs, "n", auth
        inputs = ["", "", "", "", "", "", "", "", "", "n", ""]
        with patch("builtins.input", side_effect=inputs):
            InteractiveProjectWizard(pm).edit_repository("test-project", "my-repo")
        out = capsys.readouterr().out
        assert _WARNING not in out
