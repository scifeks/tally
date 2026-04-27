"""Integration tests for ``edit_repository`` endpoint-file replacement.

Phase 9 closure: when a user edits a repo and answers "y" to replace
the endpoint file, the wizard ingests the new file via
``UserFileProvider`` + ``UrlInventoryService.ingest_user_file``, which
wipes prior USER-source rows that share the new file's destination
path (``endpoints/<uuid>/user_uploads/<basename>``) before inserting
rows for the new file.

These tests assert the wipe-and-replace semantics end-to-end:

- Same-basename replacement: rows for the prior file are wiped because
  the upload target path collides — only the new file's rows survive.
- Different-basename replacement: both files' rows coexist in
  ``url_findings`` (the wipe primitive is keyed on file_path; this is
  a documented quirk that allows multiple endpoint files per repo).
- "N" (keep): rows are untouched.
- The new upload lives under
  ``endpoints/<repo.uuid>/user_uploads/<basename>``.
"""

from __future__ import annotations

import datetime
import json
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


def _list_url_findings(base_path: Path, repo_uuid: str):  # type: ignore[no-untyped-def]
    from core.project_paths import ProjectPaths
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.repositories import RepositoryRepository
    from infrastructure.store.repositories.url_findings import UrlFindingRepository

    paths = ProjectPaths.from_canonical(base_path, "test-project")
    factory = ConnectionFactory(paths.findings_db)
    repo_row = RepositoryRepository(factory).get_by_uuid(repo_uuid)
    assert repo_row is not None, "expected repositories row after add_repository"
    return UrlFindingRepository(factory).list_for_repo(repo_row.id)


def _make_oas3_with_path(path: str) -> str:
    return json.dumps(
        {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "paths": {path: {"get": {"responses": {"200": {"description": ""}}}}},
        }
    )


def _add_repository_with_endpoint(wizard, repo_dir: Path, oas3_src: Path):  # type: ignore[no-untyped-def]
    inputs = [
        "my-repo",
        "api",
        "local",
        str(repo_dir),
        "python",
        "",  # base URLs
        "",  # test dirs
        "",  # ignore dirs
        "",  # dependencies file
        str(oas3_src),  # endpoint definition file
        "",  # auth
    ]
    with patch("builtins.input", side_effect=inputs):
        return wizard.add_repository("test-project")


def _edit_repository_replace_endpoint(
    wizard,
    repo_name: str,
    repo_dir: Path,
    new_oas3: Path,
):  # type: ignore[no-untyped-def]
    """Drive the edit-repo prompt sequence with all defaults except the
    endpoint-file replace branch."""
    edit_inputs = [
        "",  # name (keep)
        "",  # type (keep)
        "",  # mode (keep)
        str(repo_dir),  # local path (re-typed; existing not echoed)
        "",  # languages
        "",  # base urls
        "",  # test dirs
        "",  # ignore dirs
        "",  # dependencies file
        "y",  # replace endpoint file? yes
        str(new_oas3),  # new endpoint file path
        "",  # auth
    ]
    with patch("builtins.input", side_effect=edit_inputs):
        return wizard.edit_repository("test-project", repo_name)


class TestEditRepositoryEndpointFileReplacement:
    def test_replacement_with_same_basename_wipes_and_inserts(
        self, tmp_path: Path
    ) -> None:
        """Same-basename replace: old rows wiped, only new rows remain.

        The wipe primitive keys on the upload target path
        (``user_uploads/<basename>``); a same-basename re-upload collides,
        so the prior rows are removed before the new file's rows go in.
        """
        from application.project.wizard import InteractiveProjectWizard
        from core.project_paths import ProjectPaths

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        # Two source files with the SAME basename but in different dirs.
        src_a_dir = tmp_path / "src_a"
        src_a_dir.mkdir()
        src_b_dir = tmp_path / "src_b"
        src_b_dir.mkdir()
        oas3_a = src_a_dir / "api.json"
        oas3_a.write_text(_make_oas3_with_path("/users"))
        oas3_b = src_b_dir / "api.json"
        oas3_b.write_text(_make_oas3_with_path("/products"))

        base_path = tmp_path / "pm"
        pm = _setup_project(base_path)
        wizard = InteractiveProjectWizard(pm)

        repo = _add_repository_with_endpoint(wizard, repo_dir, oas3_a)
        assert repo is not None
        assert repo.uuid

        before = _list_url_findings(base_path, repo.uuid)
        assert len(before) == 1
        assert before[0].path == "/users"

        edited = _edit_repository_replace_endpoint(wizard, repo.name, repo_dir, oas3_b)
        assert edited is not None

        after = _list_url_findings(base_path, repo.uuid)
        assert len(after) == 1, (
            f"expected exactly one row after same-basename replacement, "
            f"got {len(after)}"
        )
        assert after[0].path == "/products"
        assert after[0].file_path is not None
        assert after[0].file_path.endswith("api.json")

        paths = ProjectPaths.from_canonical(base_path, "test-project")
        upload_dir = paths.endpoint_dir(repo.uuid) / "user_uploads"
        assert (upload_dir / "api.json").exists()

    def test_replacement_with_different_basename_keeps_both(
        self, tmp_path: Path
    ) -> None:
        """Different-basename replace: rows for both files coexist.

        Documented quirk: ``ingest_user_file`` wipes by the new file's
        upload path. A different basename = different upload path = no
        overlap, so prior file's rows survive. This is by design — the
        repo can carry multiple endpoint files.
        """
        from application.project.wizard import InteractiveProjectWizard
        from core.project_paths import ProjectPaths

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_a = tmp_path / "api_v1.json"
        oas3_a.write_text(_make_oas3_with_path("/users"))
        oas3_b = tmp_path / "api_v2.json"
        oas3_b.write_text(_make_oas3_with_path("/products"))

        base_path = tmp_path / "pm"
        pm = _setup_project(base_path)
        wizard = InteractiveProjectWizard(pm)

        repo = _add_repository_with_endpoint(wizard, repo_dir, oas3_a)
        assert repo is not None

        edited = _edit_repository_replace_endpoint(wizard, repo.name, repo_dir, oas3_b)
        assert edited is not None

        after = _list_url_findings(base_path, repo.uuid)
        paths_seen = sorted(r.path for r in after)
        assert paths_seen == ["/products", "/users"], (
            f"expected both files' rows to coexist, got {paths_seen}"
        )

        paths = ProjectPaths.from_canonical(base_path, "test-project")
        upload_dir = paths.endpoint_dir(repo.uuid) / "user_uploads"
        assert (upload_dir / "api_v1.json").exists()
        assert (upload_dir / "api_v2.json").exists()

    def test_replacement_with_keep_choice_leaves_rows_untouched(
        self, tmp_path: Path
    ) -> None:
        """Answering 'N' to the replace prompt does not touch url_findings."""
        from application.project.wizard import InteractiveProjectWizard

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        oas3_a = tmp_path / "api_keep.json"
        oas3_a.write_text(_make_oas3_with_path("/keep"))

        base_path = tmp_path / "pm"
        pm = _setup_project(base_path)
        wizard = InteractiveProjectWizard(pm)

        repo = _add_repository_with_endpoint(wizard, repo_dir, oas3_a)
        assert repo is not None
        before = _list_url_findings(base_path, repo.uuid)
        assert len(before) == 1
        assert before[0].path == "/keep"

        edit_inputs = [
            "",  # name (keep)
            "",  # type (keep)
            "",  # mode (keep)
            str(repo_dir),  # local path
            "",  # languages
            "",  # base urls
            "",  # test dirs
            "",  # ignore dirs
            "",  # dependencies file
            "n",  # replace endpoint file? no
            "",  # auth
        ]
        with patch("builtins.input", side_effect=edit_inputs):
            edited = wizard.edit_repository("test-project", repo.name)
        assert edited is not None

        after = _list_url_findings(base_path, repo.uuid)
        assert len(after) == 1
        assert after[0].path == "/keep"
