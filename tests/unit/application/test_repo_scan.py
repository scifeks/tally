"""Unit tests for RepoScan (application.tools.scan_types.repo)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.scan_types.models import ScanTypeConfig

_LOAD_REPOS = "application.tools.scan_types.repo.load_active_repos"
_TOOL_CONFIG = ToolExecutionConfig(noir_provider=None)


def _make_mock_repo(
    name: str = "my-repo",
    languages: list[str] | None = None,
    base_urls: list[str] | None = None,
    path: str = "",
    docker_path: str = "",
    container_name: str = "",
    oas3_path: str = "",
) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.languages = languages if languages is not None else ["python"]
    repo.base_urls = base_urls
    repo.path = path
    repo.docker_path = docker_path
    repo.container_name = container_name
    repo.oas3_path = oas3_path
    return repo


def _make_mock_tool_obj(
    name: str = "test-tool",
    scan_segment: str = "sast",
    always_run: bool = True,
    language_gates: list[str] | None = None,
) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.scan_segment = scan_segment
    t.always_run = always_run
    t.language_gates = language_gates or []
    t.requires_base_urls = False
    t.check_available.return_value = True
    t.count_findings.return_value = 0
    t.findings_exit_ok = False
    t.skip = False
    return t


def _make_config() -> ScanTypeConfig:
    prompt = MagicMock()
    prompt.confirm.return_value = True
    prompt.approve_all_remaining.return_value = None
    return ScanTypeConfig(
        project_name="test-project",
        base_path="/tmp/test",
        tool_config=_TOOL_CONFIG,
        run_id=1,
        prompt=prompt,
    )


@pytest.fixture()
def mock_config() -> Any:
    return _make_config()


@pytest.fixture()
def mock_resources() -> Any:
    registry = MagicMock()
    registry.get_all_tools.return_value = []
    registry.get_tool.return_value = None
    registry.get_tool_config.return_value = None
    return ExecutionResources(
        executor=MagicMock(),
        registry=registry,
        factory=MagicMock(),
        event_bus=MagicMock(),
        display=MagicMock(),
    )


class TestRepoScan:
    def test_repo_not_found_raises_value_error(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        with patch(_LOAD_REPOS, return_value=[]):
            with pytest.raises(ValueError, match="missing"):
                RepoScan("missing").execute(mock_config, mock_resources)

    def test_tool_not_registered_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = None

        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_factory_error_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        mock_resources.factory.create.side_effect = Exception("bad")

        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1

    def test_sca_tool_skipped_when_no_manifests(self, tmp_path: Any) -> None:
        from application.tools.scan_types.repo import RepoScan

        # tmp_path is empty — no Python manifests present.
        repo = _make_mock_repo(name="my-repo", languages=["python"], path=str(tmp_path))
        config = _make_config()
        pip_audit = MagicMock()
        pip_audit.name = "pip-audit"
        pip_audit.scan_segment = "sca"
        pip_audit.always_run = False
        pip_audit.language_gates = ["python"]
        registry = MagicMock()
        registry.get_all_tools.return_value = [pip_audit]
        registry.get_tool.return_value = pip_audit
        registry.get_tool_config.return_value = None
        resources = ExecutionResources(
            executor=MagicMock(),
            registry=registry,
            factory=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
        )

        with patch(_LOAD_REPOS, return_value=[repo]):
            summary = RepoScan("my-repo").execute(config, resources)

        # pip-audit must not appear in the tool_set — manifest gate blocks it.
        assert summary.total_tools_run == 0

    def test_sca_tool_included_when_manifests_present(self, tmp_path: Any) -> None:
        from application.tools.scan_types.repo import RepoScan

        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        repo = _make_mock_repo(name="my-repo", languages=["python"], path=str(tmp_path))
        config = _make_config()
        pip_audit = MagicMock()
        pip_audit.name = "pip-audit"
        pip_audit.scan_segment = "sca"
        pip_audit.always_run = False
        pip_audit.language_gates = ["python"]
        registry = MagicMock()
        registry.get_all_tools.return_value = [pip_audit]
        registry.get_tool.return_value = pip_audit
        # tool_config is None so it will be skipped via "not registered",
        # but it must NOT be filtered out at the manifest-gate stage.
        registry.get_tool_config.return_value = None
        resources = ExecutionResources(
            executor=MagicMock(),
            registry=registry,
            factory=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
        )

        with patch(_LOAD_REPOS, return_value=[repo]):
            summary = RepoScan("my-repo").execute(config, resources)

        # Skipped due to "not registered", not manifest gate.
        assert summary.total_tools_skipped == 1

    def test_non_sca_tool_still_uses_language_gate(self, tmp_path: Any) -> None:
        from application.tools.scan_types.repo import RepoScan

        # empty dir — no manifests — but semgrep is sast so manifest gate
        # must not apply.
        repo = _make_mock_repo(name="my-repo", languages=["python"], path=str(tmp_path))
        config = _make_config()
        semgrep = MagicMock()
        semgrep.name = "semgrep"
        semgrep.scan_segment = "sast"
        semgrep.always_run = False
        semgrep.language_gates = ["python"]
        registry = MagicMock()
        registry.get_all_tools.return_value = [semgrep]
        registry.get_tool.return_value = semgrep
        registry.get_tool_config.return_value = None
        resources = ExecutionResources(
            executor=MagicMock(),
            registry=registry,
            factory=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
        )

        with patch(_LOAD_REPOS, return_value=[repo]):
            summary = RepoScan("my-repo").execute(config, resources)

        # semgrep matched via language gate, skipped only because not
        # registered — not because of a manifest check.
        assert summary.total_tools_skipped == 1

    def test_always_run_tool_ignores_manifest_gate(self, tmp_path: Any) -> None:
        from application.tools.scan_types.repo import RepoScan

        # empty dir — no manifests.
        repo = _make_mock_repo(name="my-repo", languages=[], path=str(tmp_path))
        config = _make_config()
        osv = MagicMock()
        osv.name = "osv-scanner"
        osv.scan_segment = "sca"
        osv.always_run = True
        osv.language_gates = []
        registry = MagicMock()
        registry.get_all_tools.return_value = [osv]
        registry.get_tool.return_value = osv
        registry.get_tool_config.return_value = None
        resources = ExecutionResources(
            executor=MagicMock(),
            registry=registry,
            factory=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
        )

        with patch(_LOAD_REPOS, return_value=[repo]):
            summary = RepoScan("my-repo").execute(config, resources)

        # always_run bypasses all gates; skipped only because not registered.
        assert summary.total_tools_skipped == 1

    def test_tool_not_available_is_skipped(
        self,
        mock_config: Any,
        mock_resources: Any,
    ) -> None:
        from application.tools.scan_types.repo import RepoScan

        mock_tool = _make_mock_tool_obj("test-tool", "sast", always_run=True)
        mock_resources.registry.get_all_tools.return_value = [mock_tool]
        mock_resources.registry.get_tool.return_value = mock_tool
        mock_resources.registry.get_tool_config.return_value = MagicMock()
        created_tool = MagicMock()
        created_tool.check_available.return_value = False
        created_tool.requires_base_urls = False
        mock_resources.factory.create.return_value = created_tool

        with patch(_LOAD_REPOS, return_value=[_make_mock_repo()]):
            summary = RepoScan("my-repo").execute(mock_config, mock_resources)

        assert summary.total_tools_skipped == 1
