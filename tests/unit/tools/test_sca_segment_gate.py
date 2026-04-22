"""Unit tests for RepoSegmentScan SCA segment gate."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.tools.scan_types.resources import ExecutionResources
from domain.tools.scan_types.models import ScanTypeConfig


def _make_repo(
    name: str = "my-repo",
    path: str = "",
    docker_path: str = "",
    container_name: str = "",
    languages: list[str] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.name = name
    repo.path = path
    repo.docker_path = docker_path
    repo.container_name = container_name
    repo.languages = languages if languages is not None else ["python"]
    repo.base_urls = []
    repo.oas3_path = None
    return repo


def _make_config(repos: list) -> ScanTypeConfig:
    cm = MagicMock()
    cm.load_repositories.return_value = repos
    prompt = MagicMock()
    prompt.confirm.return_value = True
    prompt.approve_all_remaining.return_value = None
    return ScanTypeConfig(
        project_name="test",
        base_path="/tmp",
        config_manager=cm,
        run_id=1,
        prompt=prompt,
    )


def _make_resources() -> ExecutionResources:
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


class TestScaSegmentGate:
    def test_skips_entire_repo_when_no_manifests_found(self, tmp_path) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        # empty dir — no dependency manifests
        repo = _make_repo(path=str(tmp_path), languages=["python"])
        config = _make_config([repo])
        resources = _make_resources()

        summary = RepoSegmentScan(
            ["pip-audit", "npm-audit"], segment_name="sca"
        ).execute(config, resources)

        assert summary.total_tools_skipped == 2
        assert summary.total_tools_run == 0

    def test_does_not_skip_when_manifests_present(self, tmp_path) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")
        repo = _make_repo(path=str(tmp_path), languages=["python"])
        config = _make_config([repo])
        resources = _make_resources()

        # Tools won't actually run (no registry config), but we should NOT
        # hit the SCA gate — skips come from tool not found, not from gate.
        summary = RepoSegmentScan(["pip-audit"], segment_name="sca").execute(
            config, resources
        )

        # total_skipped should be 1 (tool not registered), not from SCA gate
        assert summary.total_tools_skipped == 1

    def test_gate_not_applied_for_non_sca_segment(self, tmp_path) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        # empty dir — no manifests, but segment is sast so gate must not fire
        repo = _make_repo(path=str(tmp_path), languages=["python"])
        config = _make_config([repo])
        resources = _make_resources()

        with patch(
            "application.tools.scan_types.execution.should_skip_sca_tool"
        ) as mock_gate:
            RepoSegmentScan(["semgrep"], segment_name="sast").execute(config, resources)

        mock_gate.assert_not_called()

    def test_gate_not_applied_when_segment_name_empty(self, tmp_path) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        repo = _make_repo(path=str(tmp_path), languages=["python"])
        config = _make_config([repo])
        resources = _make_resources()

        with patch(
            "application.tools.scan_types.execution.should_skip_sca_tool"
        ) as mock_gate:
            RepoSegmentScan(["semgrep"]).execute(config, resources)

        mock_gate.assert_not_called()

    def test_docker_repo_uses_docker_manifest_check(self) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        repo = _make_repo(
            path="",
            docker_path="/app",
            container_name="my-container",
            languages=["python"],
        )
        config = _make_config([repo])
        pip_audit_mock = MagicMock()
        pip_audit_mock.language_gates = ["python"]
        pip_audit_mock.scan_segment = "sca"

        registry = MagicMock()
        registry.get_all_tools.return_value = []
        registry.get_tool.return_value = pip_audit_mock
        registry.get_tool_config.return_value = None
        resources = ExecutionResources(
            executor=MagicMock(),
            registry=registry,
            factory=MagicMock(),
            event_bus=MagicMock(),
            display=MagicMock(),
        )

        with patch(
            "application.tools.scan_types.execution.has_manifests_for_language",
            return_value=False,
        ) as mock_manifest_check:
            summary = RepoSegmentScan(["pip-audit"], segment_name="sca").execute(
                config, resources
            )

        mock_manifest_check.assert_called_once_with("/app", "python", "my-container")
        assert summary.total_tools_skipped == 1

    def test_repo_with_no_path_and_no_docker_path_is_skipped(self) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        repo = _make_repo(path="", docker_path="", container_name="")
        config = _make_config([repo])
        resources = _make_resources()

        summary = RepoSegmentScan(["pip-audit"], segment_name="sca").execute(
            config, resources
        )

        assert summary.total_tools_skipped == 1

    def test_multiple_repos_gates_are_independent(self, tmp_path) -> None:
        from application.tools.scan_types.repo_segment import RepoSegmentScan

        # repo A has manifests, repo B does not
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        dir_b = tmp_path / "b"
        dir_b.mkdir()
        (dir_a / "requirements.txt").write_text("requests==2.28.0\n")

        repo_a = _make_repo(name="a", path=str(dir_a), languages=["python"])
        repo_b = _make_repo(name="b", path=str(dir_b), languages=["python"])

        config = _make_config([repo_a, repo_b])
        resources = _make_resources()

        summary = RepoSegmentScan(["pip-audit"], segment_name="sca").execute(
            config, resources
        )

        # repo_a: tool not registered (1 skip) — gate passed
        # repo_b: gate skip (1 skip)
        assert summary.total_tools_skipped == 2
