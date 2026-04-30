"""Integration tests: purge behaviour for endpoint artifacts.

``_delete_merged_endpoints`` removes JIT-rebuilt merged files under
``endpoints/<repo>/`` while leaving ``config/endpoints/`` untouched.
The merged artifacts are rebuilt from ``url_findings`` rows.
"""

from __future__ import annotations

import datetime
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.manager import ConfigManager  # noqa: E402
from core.config.schemas import ProjectConfig  # noqa: E402

pytestmark = pytest.mark.integration


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


def _save_project(base_path: Path, project_name: str) -> None:
    _write_global_config(base_path)
    manager = ConfigManager(str(base_path))
    pc = ProjectConfig(
        project_name=project_name,
        created=datetime.datetime.now().isoformat(),
    )
    manager.save_project_config(project_name, pc)


def _make_repl(tmp_path: Path, project_name: str) -> MagicMock:
    repl = MagicMock()
    repl.active_project = project_name
    repl.base_path = str(tmp_path)
    return repl


class TestPurgePreservesConfigEndpoints:
    def test_tool_output_purge_does_not_touch_config_endpoints(
        self, tmp_path: Path
    ) -> None:
        """``config/endpoints/<repo>/`` survives a full tool-output purge."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "test-proj"
        project_dir = tmp_path / "projects" / project_name

        semgrep_dir = project_dir / "tool_outputs" / "semgrep"
        semgrep_dir.mkdir(parents=True, exist_ok=True)
        output_file = semgrep_dir / "result.json"
        output_file.write_text("{}")

        seed_dir = project_dir / "config" / "endpoints" / "my-repo"
        seed_dir.mkdir(parents=True, exist_ok=True)
        original_dir = seed_dir / "original"
        original_dir.mkdir()
        original_file = original_dir / "api.json"
        original_file.write_text('{"openapi": "3.0.0"}')
        seed_file = seed_dir / "seed.json"
        seed_file.write_text('{"openapi": "3.0.3", "info": {}, "paths": {}}')

        pc = PurgeCommand(_make_repl(tmp_path, project_name))
        pc._delete_tool_output_files(tools=None)

        assert original_file.exists(), "original seed must survive tool-output purge"
        assert seed_file.exists(), "seed.json must survive tool-output purge"
        assert not output_file.exists(), "tool_outputs/ file must be deleted"


class TestDeleteMergedEndpoints:
    def _setup(
        self,
        tmp_path: Path,
        project_name: str,
        repo_name: str,
    ) -> tuple[Path, Path]:
        _save_project(tmp_path, project_name)

        merged_dir = tmp_path / "projects" / project_name / "endpoints" / repo_name
        merged_dir.mkdir(parents=True, exist_ok=True)
        oas3 = merged_dir / "merged_oas3.json"
        urls = merged_dir / "merged_urls.txt"
        oas3.write_text('{"openapi": "3.0.0"}')
        urls.write_text("http://localhost/api\n")
        return oas3, urls

    def test_delete_merged_removes_files(self, tmp_path: Path) -> None:
        """``_delete_merged_endpoints`` wipes merged artifact files."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "test-proj"
        repo_name = "my-repo"
        oas3, urls = self._setup(tmp_path, project_name, repo_name)

        pc = PurgeCommand(_make_repl(tmp_path, project_name))
        pc._delete_merged_endpoints()

        assert not oas3.exists(), "merged_oas3.json must be deleted"
        assert not urls.exists(), "merged_urls.txt must be deleted"

    def test_delete_merged_leaves_config_endpoints_intact(self, tmp_path: Path) -> None:
        """``config/endpoints/`` is never touched by ``_delete_merged_endpoints``."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "test-proj"
        repo_name = "my-repo"
        self._setup(tmp_path, project_name, repo_name)

        seed_dir = (
            tmp_path / "projects" / project_name / "config" / "endpoints" / repo_name
        )
        seed_dir.mkdir(parents=True, exist_ok=True)
        seed_file = seed_dir / "seed.json"
        seed_file.write_text('{"openapi": "3.0.3", "info": {}, "paths": {}}')

        pc = PurgeCommand(_make_repl(tmp_path, project_name))
        pc._delete_merged_endpoints()

        assert seed_file.exists(), "seed.json must survive _delete_merged_endpoints"


class TestCmdPurgeMergedPrompt:
    """``cmd_purge``: second y/N prompt for merged endpoint cleanup."""

    def _setup(
        self, tmp_path: Path, project_name: str, repo_name: str
    ) -> tuple[Path, Path]:
        _save_project(tmp_path, project_name)

        project_dir = tmp_path / "projects" / project_name
        sqlite_dir = project_dir / "sqlite"
        sqlite_dir.mkdir(parents=True, exist_ok=True)

        merged_dir = project_dir / "endpoints" / repo_name
        merged_dir.mkdir(parents=True, exist_ok=True)
        oas3 = merged_dir / "merged_oas3.json"
        urls = merged_dir / "merged_urls.txt"
        oas3.write_text("{}")
        urls.write_text("http://localhost/\n")
        return oas3, urls

    def test_answering_n_leaves_merged_intact(self, tmp_path: Path) -> None:
        """Answering 'n' to the merged-URL prompt keeps merged files."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "purge-n-test"
        repo_name = "api"
        oas3, urls = self._setup(tmp_path, project_name, repo_name)

        repl = _make_repl(tmp_path, project_name)
        mock_rag = MagicMock()
        mock_rag.count_documents.return_value = 1
        mock_rag.delete_findings.return_value = 1

        pc = PurgeCommand(repl)
        with (
            patch.object(pc, "_get_rag_engine", return_value=mock_rag),
            patch("builtins.input", side_effect=["y", "n"]),
            patch.object(pc, "_count_sqlite_findings", return_value=0),
            patch.object(pc, "_purge_sqlite"),
        ):
            pc.cmd_purge("purge", [])

        assert oas3.exists(), "merged_oas3.json must survive when user answers 'n'"
        assert urls.exists(), "merged_urls.txt must survive when user answers 'n'"

    def test_answering_y_deletes_merged_files(self, tmp_path: Path) -> None:
        """Answering 'y' to the merged-URL prompt deletes merged files."""
        from application.repl.commands.purge import PurgeCommand

        project_name = "purge-y-test"
        repo_name = "api"
        oas3, urls = self._setup(tmp_path, project_name, repo_name)

        seed_dir = (
            tmp_path / "projects" / project_name / "config" / "endpoints" / repo_name
        )
        seed_dir.mkdir(parents=True, exist_ok=True)
        seed_file = seed_dir / "seed.json"
        seed_file.write_text('{"openapi": "3.0.3", "info": {}, "paths": {}}')

        repl = _make_repl(tmp_path, project_name)
        mock_rag = MagicMock()
        mock_rag.count_documents.return_value = 1
        mock_rag.delete_findings.return_value = 1

        pc = PurgeCommand(repl)
        with (
            patch.object(pc, "_get_rag_engine", return_value=mock_rag),
            patch("builtins.input", side_effect=["y", "y"]),
            patch.object(pc, "_count_sqlite_findings", return_value=0),
            patch.object(pc, "_purge_sqlite"),
        ):
            pc.cmd_purge("purge", [])

        assert not oas3.exists(), (
            "merged_oas3.json must be deleted when user answers 'y'"
        )
        assert not urls.exists(), (
            "merged_urls.txt must be deleted when user answers 'y'"
        )
        assert seed_file.exists(), "seed.json must survive purge"
