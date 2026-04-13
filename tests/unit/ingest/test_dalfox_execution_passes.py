"""Unit tests for DalFoxLocalTool.build_command and build_execution_passes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.dalfox import (
    DalFoxLocalTool,
    _build_seeds_from_noir,
    _build_seeds_from_oas3,
    _write_seeds_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    base_urls: list[str] | None = None,
    oas3_path: str = "",
    dalfox_mode: str = "crawl",
    dalfox_headers: dict[str, str] | None = None,
    node_app: bool = False,
    path: str = "/repo",
) -> Repository:
    return Repository.model_construct(
        name="testrepo",
        type=["api"],
        path=path,
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=base_urls or ["http://localhost:8080"],
        test_dirs=[],
        ignore_dirs=[],
        oas3_path=oas3_path,
        node_app=node_app,
        dalfox_mode=dalfox_mode,
        dalfox_headers=dalfox_headers or {},
    )


def _make_context(repo: Repository, base_path: str) -> ExecutionContext:
    registry = MagicMock()
    config_manager = MagicMock()
    return ExecutionContext(
        project_name="testproject",
        base_path=base_path,
        repo=repo,
        config_manager=config_manager,
        registry=registry,
        is_docker=False,
    )


# ---------------------------------------------------------------------------
# BaseDalFoxTool properties
# ---------------------------------------------------------------------------


class TestBaseProperties:
    def test_name(self) -> None:
        assert DalFoxLocalTool().name == "dalfox"

    def test_requires_base_urls(self) -> None:
        assert DalFoxLocalTool().requires_base_urls is True

    def test_findings_exit_ok(self) -> None:
        assert DalFoxLocalTool().findings_exit_ok is True

    def test_scan_segment(self) -> None:
        assert DalFoxLocalTool().scan_segment == "web"

    def test_category(self) -> None:
        assert DalFoxLocalTool().category == "web"

    def test_always_run_true(self) -> None:
        assert DalFoxLocalTool().always_run is True

    def test_skip_is_false(self) -> None:
        assert DalFoxLocalTool().skip is False

    def test_should_visualize_is_true(self) -> None:
        assert DalFoxLocalTool().should_visualize is True

    def test_count_findings_from_summary(self) -> None:
        tool = DalFoxLocalTool()
        parsed = {"findings": [{}, {}], "summary": {"total_findings": 2}}
        assert tool.count_findings(parsed) == 2

    def test_count_findings_fallback_to_list_length(self) -> None:
        tool = DalFoxLocalTool()
        parsed = {"findings": [{}, {}, {}]}
        assert tool.count_findings(parsed) == 3

    def test_count_findings_empty(self) -> None:
        tool = DalFoxLocalTool()
        assert tool.count_findings({}) == 0


# ---------------------------------------------------------------------------
# build_command — url mode
# ---------------------------------------------------------------------------


class TestBuildCommandUrl:
    def test_url_mode_uses_url_subcommand(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "url" in cmd
        assert "http://localhost:8080" in cmd

    def test_url_mode_includes_format_json(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "--format" in cmd
        idx = cmd.index("--format")
        assert cmd[idx + 1] == "json"

    def test_url_mode_includes_output_file(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "-o" in cmd
        idx = cmd.index("-o")
        assert cmd[idx + 1] == output

    def test_url_mode_includes_no_spinner(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "--no-spinner" in cmd

    def test_url_mode_includes_no_color(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "--no-color" in cmd

    def test_url_mode_includes_deep_domxss(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "--deep-domxss" in cmd

    def test_sets_last_output_path(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert tool._last_output_path == Path(output)


# ---------------------------------------------------------------------------
# build_command — seeds (file) mode
# ---------------------------------------------------------------------------


class TestBuildCommandSeeds:
    def test_seeds_mode_uses_file_subcommand(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(seeds_file=seeds, output_file=output)
        assert "file" in cmd
        assert seeds in cmd

    def test_seeds_mode_omits_url_subcommand(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(seeds_file=seeds, output_file=output)
        assert "url" not in cmd

    def test_seeds_mode_still_includes_format_json(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(seeds_file=seeds, output_file=output)
        assert "--format" in cmd
        assert "json" in cmd

    def test_seeds_mode_includes_deep_domxss(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(seeds_file=seeds, output_file=output)
        assert "--deep-domxss" in cmd


# ---------------------------------------------------------------------------
# build_command — headers
# ---------------------------------------------------------------------------


class TestBuildCommandHeaders:
    def test_no_headers_kwarg_omits_h_flag(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        cmd = tool.build_command(base_url="http://localhost:8080", output_file=output)
        assert "-H" not in cmd

    def test_single_header_adds_h_flag(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        headers = {"Cookie": "session=abc123"}
        cmd = tool.build_command(
            base_url="http://localhost:8080", output_file=output, headers=headers
        )
        assert "-H" in cmd

    def test_header_value_formatted_as_key_colon_value(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        headers = {"Cookie": "session=abc123"}
        cmd = tool.build_command(
            base_url="http://localhost:8080", output_file=output, headers=headers
        )
        idx = cmd.index("-H")
        assert cmd[idx + 1] == "Cookie: session=abc123"

    def test_multiple_headers_produce_multiple_h_flags(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        output = str(tmp_path / "out.json")
        headers = {"Cookie": "s=1", "X-Custom": "val"}
        cmd = tool.build_command(
            base_url="http://localhost:8080", output_file=output, headers=headers
        )
        assert cmd.count("-H") == 2

    def test_repo_dalfox_headers_passed_to_kwargs(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_headers={"Cookie": "PHPSESSID=xyz"})
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("headers") == {"Cookie": "PHPSESSID=xyz"}

    def test_repo_empty_dalfox_headers_not_in_kwargs(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_headers={})
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert "headers" not in passes[0].kwargs


# ---------------------------------------------------------------------------
# build_command — error cases
# ---------------------------------------------------------------------------


class TestBuildCommandErrors:
    def test_missing_base_url_and_seeds_raises(self, tmp_path: Path) -> None:
        tool = DalFoxLocalTool()
        with pytest.raises(ValueError, match="base_url or seeds_file"):
            tool.build_command(output_file=str(tmp_path / "out.json"))

    def test_missing_output_file_raises(self) -> None:
        tool = DalFoxLocalTool()
        with pytest.raises(ValueError, match="output_file"):
            tool.build_command(base_url="http://localhost:8080")


# ---------------------------------------------------------------------------
# build_execution_passes — crawl mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesOutputFilePath:
    def test_output_file_is_absolute_when_base_path_is_dot(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, ".")
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        output_file = passes[0].kwargs.get("output_file", "")
        assert Path(str(output_file)).is_absolute(), (
            f"output_file must be absolute; got {output_file!r}"
        )

    def test_output_file_is_absolute_when_base_path_is_absolute(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        output_file = passes[0].kwargs.get("output_file", "")
        assert Path(str(output_file)).is_absolute()


class TestBuildExecutionPassesCrawl:
    def test_crawl_mode_returns_one_pass(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1

    def test_crawl_mode_kwargs_contain_base_url(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"

    def test_crawl_mode_kwargs_no_seeds_file(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert "seeds_file" not in passes[0].kwargs

    def test_output_dir_created(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        DalFoxLocalTool().build_execution_passes(ctx)
        expected = tmp_path / "projects" / "testproject" / "tool_outputs" / "dalfox"
        assert expected.exists()

    def test_label_suffix_is_repo_name(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].label_suffix == "testrepo"

    def test_default_empty_mode_treated_as_crawl(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"


# ---------------------------------------------------------------------------
# build_execution_passes — noir mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesNoir:
    def test_noir_mode_with_oas3_uses_seeds(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {"/api/users": {}, "/api/items": {}}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        repo = _make_repo(dalfox_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert "seeds_file" in passes[0].kwargs
        assert "base_url" not in passes[0].kwargs

    def test_noir_seeds_file_contains_correct_urls(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {"/api/users": {}}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        repo = _make_repo(dalfox_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        seeds_path = Path(passes[0].kwargs["seeds_file"])
        urls = seeds_path.read_text(encoding="utf-8").strip().splitlines()
        assert "http://localhost:8080/api/users" in urls

    def test_noir_mode_no_oas3_falls_back_to_crawl(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"
        assert "seeds_file" not in passes[0].kwargs

    def test_noir_mode_empty_oas3_paths_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        repo = _make_repo(dalfox_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"

    def test_noir_mode_picks_lexicographically_last_oas3(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        old_oas3 = {"openapi": "3.0.0", "paths": {"/old": {}}}
        new_oas3 = {"openapi": "3.0.0", "paths": {"/new": {}}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(
            json.dumps(old_oas3)
        )
        (noir_dir / "testrepo_20240201T000000_oas3.json").write_text(
            json.dumps(new_oas3)
        )
        repo = _make_repo(dalfox_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        seeds_path = Path(passes[0].kwargs["seeds_file"])
        content = seeds_path.read_text(encoding="utf-8")
        assert "/new" in content
        assert "/old" not in content


# ---------------------------------------------------------------------------
# build_execution_passes — provided mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesProvided:
    def test_provided_mode_with_oas3_path_uses_seeds(self, tmp_path: Path) -> None:
        oas3_file = tmp_path / "endpoints.json"
        oas3_file.write_text(
            json.dumps({"openapi": "3.0.0", "paths": {"/api/v1/health": {}}})
        )
        repo = _make_repo(dalfox_mode="provided", oas3_path=str(oas3_file))
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert "seeds_file" in passes[0].kwargs

    def test_provided_mode_seeds_url_correct(self, tmp_path: Path) -> None:
        oas3_file = tmp_path / "endpoints.json"
        oas3_file.write_text(
            json.dumps({"openapi": "3.0.0", "paths": {"/api/v1/health": {}}})
        )
        repo = _make_repo(dalfox_mode="provided", oas3_path=str(oas3_file))
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        seeds_path = Path(passes[0].kwargs["seeds_file"])
        urls = seeds_path.read_text(encoding="utf-8").strip().splitlines()
        assert "http://localhost:8080/api/v1/health" in urls

    def test_provided_mode_empty_oas3_path_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(dalfox_mode="provided", oas3_path="")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"

    def test_provided_mode_missing_oas3_file_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            dalfox_mode="provided",
            oas3_path=str(tmp_path / "nonexistent.json"),
        )
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"


# ---------------------------------------------------------------------------
# Seeds helpers
# ---------------------------------------------------------------------------


class TestWriteSeedsFile:
    def test_writes_one_url_per_line(self, tmp_path: Path) -> None:
        paths = ["/a", "/b", "/c"]
        result = _write_seeds_file(paths, "http://localhost:8080", tmp_path, "ts1")
        assert result is not None
        lines = Path(result).read_text(encoding="utf-8").strip().splitlines()
        assert lines == [
            "http://localhost:8080/a",
            "http://localhost:8080/b",
            "http://localhost:8080/c",
        ]

    def test_base_url_trailing_slash_stripped(self, tmp_path: Path) -> None:
        result = _write_seeds_file(["/a"], "http://localhost:8080/", tmp_path, "ts2")
        assert result is not None
        lines = Path(result).read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["http://localhost:8080/a"]

    def test_path_without_leading_slash_is_handled(self, tmp_path: Path) -> None:
        result = _write_seeds_file(
            ["api/users"], "http://localhost:8080", tmp_path, "ts3"
        )
        assert result is not None
        lines = Path(result).read_text(encoding="utf-8").strip().splitlines()
        assert lines == ["http://localhost:8080/api/users"]

    def test_empty_paths_returns_none(self, tmp_path: Path) -> None:
        result = _write_seeds_file([], "http://localhost:8080", tmp_path, "ts4")
        assert result is None


class TestBuildSeedsFromNoir:
    def test_returns_none_when_noir_dir_absent(self, tmp_path: Path) -> None:
        result = _build_seeds_from_noir(
            str(tmp_path), "proj", "repo", "http://x.com", tmp_path, "ts"
        )
        assert result is None

    def test_returns_none_when_no_matching_files(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        result = _build_seeds_from_noir(
            str(tmp_path), "proj", "repo", "http://x.com", tmp_path, "ts"
        )
        assert result is None

    def test_returns_seeds_file_path_on_success(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {"/ep": {}}}
        (noir_dir / "repo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        result = _build_seeds_from_noir(
            str(tmp_path), "proj", "repo", "http://x.com", tmp_path, "ts"
        )
        assert result is not None
        assert Path(result).exists()


class TestBuildSeedsFromOas3:
    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = _build_seeds_from_oas3(
            tmp_path / "missing.json", "http://x.com", tmp_path, "ts"
        )
        assert result is None

    def test_returns_seeds_file_on_valid_oas3(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text(json.dumps({"openapi": "3.0.0", "paths": {"/a": {}}}))
        result = _build_seeds_from_oas3(f, "http://x.com", tmp_path, "ts")
        assert result is not None

    def test_returns_none_for_empty_paths(self, tmp_path: Path) -> None:
        f = tmp_path / "spec.json"
        f.write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
        result = _build_seeds_from_oas3(f, "http://x.com", tmp_path, "ts")
        assert result is None
