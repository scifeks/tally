"""Unit tests for SemgrepLocalTool.build_execution_passes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.semgrep import SemgrepLocalTool


def _make_repo(path: str, test_dirs: list[str]) -> Repository:
    return Repository.model_construct(
        name="test-repo",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs,
        ignore_dirs=[],
    )


def _make_context(repo: Repository) -> ExecutionContext:
    registry = MagicMock()
    registry.get_repo_path.return_value = repo.path or "/repo"
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=False,
    )


class TestSemgrepBuildExecutionPasses:
    def test_passes_exclude_from_test_dirs(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(str(repo_dir), ["tests", "spec"])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert passes[0].kwargs["exclude"] == ["tests", "spec"]

    def test_no_exclude_when_empty_and_no_auto_detect(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(str(repo_dir), [])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert "exclude" not in passes[0].kwargs

    def test_no_auto_detect_when_config_dirs_empty(self, tmp_path: Path) -> None:
        # Auto-detection from filesystem was removed; exclusions come from repo
        # config only. Even with a tests/ dir present, no exclude is applied
        # when test_dirs=[] and ignore_dirs=[].
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        (repo_dir / "tests").mkdir()
        repo = _make_repo(str(repo_dir), [])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1
        assert "exclude" not in passes[0].kwargs
