"""Unit tests for SemgrepLocalTool.build_execution_passes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from core.config.schemas.repo_service import RepoService
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.semgrep import SemgrepLocalTool


def _make_repo(path: str, test_dirs: list[str]) -> Repository:
    service = RepoService.model_construct(
        name="default",
        relative_path="",
        type=["api"],
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs,
        ignore_dirs=[],
    )
    return Repository.model_construct(
        name="test-repo",
        path=path,
        services=[service],
    )


def _make_context(repo: Repository) -> ExecutionContext:
    from core.config.schemas import build_excluded_dirs

    registry = MagicMock()
    registry.get_repo_path.return_value = repo.path or "/repo"
    service = (
        repo.services[0]
        if repo.services
        else RepoService.model_construct(name="default")
    )
    excluded_dirs = build_excluded_dirs(service) if service else []
    return ExecutionContext(
        project_name="test",
        base_path="/tmp",
        repo=repo,
        service=service,
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=False,
        excluded_dirs=excluded_dirs,
    )


class TestSemgrepBuildExecutionPasses:
    def test_passes_exclude_from_test_dirs(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(str(repo_dir), ["tests", "spec"])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 2
        exclude = passes[0].kwargs.get("exclude", [])
        assert "tests" in exclude
        assert "Tests" in exclude
        assert "spec" in exclude
        assert "Spec" in exclude

    def test_no_exclude_when_empty_and_no_auto_detect(self, tmp_path: Path) -> None:
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo = _make_repo(str(repo_dir), [])
        ctx = _make_context(repo)
        tool = SemgrepLocalTool(config=None)
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 2
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
        assert len(passes) == 2
        assert "exclude" not in passes[0].kwargs
