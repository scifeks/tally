"""Integration tests for ``edit_repository`` endpoint-file replacement.

Each upload lands in a fresh ``endpoints/<repo-name>-<epoch>/`` sibling
directory; prior uploads are kept as history. The repo's
``url_seed_file`` column points at the most-recent upload path. Per-file
``url_findings`` rows accumulate (each upload has its own ``file_path``).

These tests cover:

- Replace branch (any basename): a new sibling dir is created, rows for
  both files coexist in ``url_findings``, and ``url_seed_file`` points
  at the latest upload.
- "N" (keep): rows and seed-file pointer are untouched.
"""

from __future__ import annotations

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
    from infrastructure.store.connection import ConnectionFactory

    _write_global_config(base_path)

    def schema_init(db_path):
        ConnectionFactory(db_path).init_schema()

    return ProjectManager(base_path=str(base_path), schema_initializer=schema_init)


def _setup_project(base_path: Path):  # type: ignore[no-untyped-def]
    pm = _make_pm(base_path)
    pm.create_project_dirs("test-project")
    pm.save_project("test-project")
    return pm


def _list_url_findings(base_path: Path, repo_id: int):  # type: ignore[no-untyped-def]
    from core.project_paths import ProjectPaths
    from infrastructure.store.connection import ConnectionFactory
    from infrastructure.store.repositories.url_findings import UrlFindingRepository

    paths = ProjectPaths.from_canonical(base_path, "test-project")
    factory = ConnectionFactory(paths.findings_db)
    return UrlFindingRepository(factory).list_for_repo(repo_id)


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
        """Same-basename replace: each upload lands in a fresh sibling dir.

        Two uploads with the same basename create two distinct sibling
        dirs (different epochs), both files' rows accumulate, and the
        seed-file pointer tracks the latest upload.
        """
        from application.project.wizard import InteractiveProjectWizard
        from core.project_paths import ProjectPaths

        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
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
        assert repo.id is not None

        before = _list_url_findings(base_path, repo.id)
        assert len(before) == 1
        assert before[0].path == "/users"

        edited = _edit_repository_replace_endpoint(wizard, repo.name, repo_dir, oas3_b)
        assert edited is not None
        assert edited.url_seed_file is not None

        after = _list_url_findings(base_path, repo.id)
        paths_seen = sorted(r.path for r in after)
        assert paths_seen == ["/products", "/users"]

        paths = ProjectPaths.from_canonical(base_path, "test-project")
        sibling_dirs = sorted(
            p.name
            for p in paths.endpoints_dir.iterdir()
            if p.is_dir() and p.name.startswith(f"{repo.name}-")
        )
        assert len(sibling_dirs) == 2
        for d in sibling_dirs:
            assert (paths.endpoints_dir / d / "api.json").exists()

        # url_seed_file points at the latest upload.
        assert Path(edited.url_seed_file).name == "api.json"
        assert Path(edited.url_seed_file).parent.parent == paths.endpoints_dir
        assert Path(edited.url_seed_file).parent.name == sibling_dirs[-1]

    def test_replacement_with_different_basename_keeps_both(
        self, tmp_path: Path
    ) -> None:
        """Different-basename replace: rows for both files coexist; both
        sibling dirs are kept on disk."""
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
        assert repo.id is not None

        edited = _edit_repository_replace_endpoint(wizard, repo.name, repo_dir, oas3_b)
        assert edited is not None

        after = _list_url_findings(base_path, repo.id)
        paths_seen = sorted(r.path for r in after)
        assert paths_seen == ["/products", "/users"], (
            f"expected both files' rows to coexist, got {paths_seen}"
        )

        paths = ProjectPaths.from_canonical(base_path, "test-project")
        sibling_dirs = sorted(
            p.name
            for p in paths.endpoints_dir.iterdir()
            if p.is_dir() and p.name.startswith(f"{repo.name}-")
        )
        assert len(sibling_dirs) == 2
        basenames = {
            (paths.endpoints_dir / d).iterdir().__next__().name for d in sibling_dirs
        }
        assert basenames == {"api_v1.json", "api_v2.json"}

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
        assert repo.id is not None
        seed_before = repo.url_seed_file

        before = _list_url_findings(base_path, repo.id)
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
        assert edited.url_seed_file == seed_before

        after = _list_url_findings(base_path, repo.id)
        assert len(after) == 1
        assert after[0].path == "/keep"
