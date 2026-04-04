"""Unit tests for NoirLocalTool.build_command and build_execution_passes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.noir import NoirLocalTool


def _make_repo(path: str) -> Repository:
    return Repository.model_construct(
        name="dvna",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["javascript/typescript"],
        base_urls=["http://localhost:9090"],
        test_dirs=[],
        ignore_dirs=[],
    )


def _make_context(repo: Repository, base_path: str) -> ExecutionContext:
    registry = MagicMock()
    registry.get_repo_path.return_value = repo.path or "/repo"
    config_manager = MagicMock()
    return ExecutionContext(
        project_name="DVPA",
        base_path=base_path,
        repo=repo,
        config_manager=config_manager,
        registry=registry,
        is_docker=False,
    )


# ---------------------------------------------------------------------------
# build_command
# ---------------------------------------------------------------------------


class TestNoirBuildCommand:
    def test_valid_invocation_returns_correct_argv(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        out = str(tmp_path / "out.json")
        tool = NoirLocalTool()
        cmd = tool.build_command(source_path=str(src), output_file=out)
        assert cmd[0] == "noir"
        assert "-b" in cmd
        assert str(src) in cmd
        assert "-f" in cmd
        assert "oas3" in cmd
        assert "--no-log" in cmd
        assert "-o" in cmd
        assert out in cmd

    def test_sets_last_report_path(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        out = str(tmp_path / "report.json")
        tool = NoirLocalTool()
        tool.build_command(source_path=str(src), output_file=out)
        assert tool._last_report_path is not None
        assert tool._last_report_path.name == "report.json"

    def test_missing_source_path_raises(self) -> None:
        tool = NoirLocalTool()
        with pytest.raises(ValueError, match="source_path"):
            tool.build_command(output_file="/tmp/out.json")

    def test_nonexistent_source_path_raises(self, tmp_path: Path) -> None:
        tool = NoirLocalTool()
        with pytest.raises(ValueError, match="does not exist"):
            tool.build_command(
                source_path=str(tmp_path / "missing"),
                output_file=str(tmp_path / "out.json"),
            )

    def test_missing_output_file_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        with pytest.raises(ValueError, match="output_file"):
            tool.build_command(source_path=str(src))

    def test_output_file_resolved_to_absolute(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(source_path=str(src), output_file="relative.json")
        out_idx = cmd.index("-o") + 1
        assert Path(cmd[out_idx]).is_absolute()


# ---------------------------------------------------------------------------
# build_execution_passes
# ---------------------------------------------------------------------------


class TestNoirBuildExecutionPasses:
    def test_returns_one_pass(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 1

    def test_pass_kwargs_include_source_path(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "source_path" in passes[0].kwargs
        assert passes[0].kwargs["source_path"] == str(src)

    def test_pass_kwargs_include_output_file(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        output_file: str = passes[0].kwargs["output_file"]
        assert output_file.endswith("_oas3.json")
        assert "noir" in output_file

    def test_output_dir_created(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        tool.build_execution_passes(ctx)
        expected_dir = tmp_path / "projects" / "DVPA" / "tool_outputs" / "noir"
        assert expected_dir.exists()

    def test_label_suffix_is_repo_name(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert passes[0].label_suffix == "dvna"
