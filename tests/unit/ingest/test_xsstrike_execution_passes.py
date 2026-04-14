"""Unit tests for XSSTrikeLocalTool.build_command and build_execution_passes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.xsstrike import (
    XSSTrikeLocalTool,
    _build_seeds_from_noir,
    _build_seeds_from_oas3,
    _recommended_thread_count,
    _write_seeds_file,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    base_urls: list[str] | None = None,
    oas3_path: str = "",
    xsstrike_mode: str = "crawl",
    xsstrike_crawl_level: int = 10,
    xsstrike_headers: dict[str, str] | None = None,
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
        xsstrike_mode=xsstrike_mode,
        xsstrike_crawl_level=xsstrike_crawl_level,
        xsstrike_headers=xsstrike_headers or {},
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
# BaseXSStrikeTool properties
# ---------------------------------------------------------------------------


class TestBaseProperties:
    def test_name(self) -> None:
        assert XSSTrikeLocalTool().name == "xsstrike"

    def test_requires_base_urls(self) -> None:
        assert XSSTrikeLocalTool().requires_base_urls is True

    def test_findings_exit_ok(self) -> None:
        assert XSSTrikeLocalTool().findings_exit_ok is True

    def test_scan_segment(self) -> None:
        assert XSSTrikeLocalTool().scan_segment == "web"

    def test_category(self) -> None:
        assert XSSTrikeLocalTool().category == "web"

    def test_always_run_true(self) -> None:
        assert XSSTrikeLocalTool().always_run is True

    def test_count_findings_from_summary(self) -> None:
        tool = XSSTrikeLocalTool()
        parsed = {"findings": [{}, {}], "summary": {"total_findings": 2}}
        assert tool.count_findings(parsed) == 2

    def test_count_findings_fallback_to_list_length(self) -> None:
        tool = XSSTrikeLocalTool()
        parsed = {"findings": [{}, {}, {}]}
        assert tool.count_findings(parsed) == 3

    def test_count_findings_empty(self) -> None:
        tool = XSSTrikeLocalTool()
        assert tool.count_findings({}) == 0


# ---------------------------------------------------------------------------
# build_command — crawl mode
# ---------------------------------------------------------------------------


class TestBuildCommandCrawl:
    def test_crawl_mode_uses_u_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "-u" in cmd
        assert "http://localhost:8080" in cmd

    def test_crawl_mode_includes_crawl_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--crawl" in cmd

    def test_crawl_mode_includes_skip_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--skip" in cmd

    def test_crawl_mode_includes_file_log_level(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--file-log-level" in cmd
        idx = cmd.index("--file-log-level")
        assert cmd[idx + 1] == "DEBUG"

    def test_crawl_mode_includes_log_file(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--log-file" in cmd
        idx = cmd.index("--log-file")
        assert cmd[idx + 1] == log

    def test_sets_last_log_path(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert tool._last_log_path == Path(log)


# ---------------------------------------------------------------------------
# build_command — seeds mode
# ---------------------------------------------------------------------------


class TestBuildCommandSeeds:
    def test_seeds_mode_uses_seeds_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(seeds_file=seeds, log_file=log)
        assert "--seeds" in cmd
        idx = cmd.index("--seeds")
        assert cmd[idx + 1] == seeds

    def test_seeds_mode_omits_u_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(seeds_file=seeds, log_file=log)
        assert "-u" not in cmd

    def test_seeds_mode_still_includes_crawl_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(seeds_file=seeds, log_file=log)
        assert "--crawl" in cmd


# ---------------------------------------------------------------------------
# build_command — error cases
# ---------------------------------------------------------------------------


class TestBuildCommandErrors:
    def test_missing_base_url_and_seeds_raises(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        with pytest.raises(ValueError, match="base_url or seeds_file"):
            tool.build_command(log_file=str(tmp_path / "out.log"))

    def test_missing_log_file_raises(self) -> None:
        tool = XSSTrikeLocalTool()
        with pytest.raises(ValueError, match="log_file"):
            tool.build_command(base_url="http://localhost:8080")


# ---------------------------------------------------------------------------
# build_execution_passes — crawl mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesLogFilePath:
    def test_log_file_is_absolute_when_base_path_is_dot(self, tmp_path: Path) -> None:
        """log_file must be absolute so xsstrike can write it regardless of its CWD.

        XSStrike changes its working directory to its own install root on startup.
        A relative log_file path resolves against that directory, not the tally
        project root, causing a FileNotFoundError and an instant-exit 0-result scan.
        """
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, ".")
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        log_file = passes[0].kwargs.get("log_file", "")
        assert Path(str(log_file)).is_absolute(), (
            f"log_file must be absolute; got {log_file!r}"
        )

    def test_log_file_is_absolute_when_base_path_is_absolute(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        log_file = passes[0].kwargs.get("log_file", "")
        assert Path(str(log_file)).is_absolute()


class TestBuildExecutionPassesCrawl:
    def test_crawl_mode_returns_one_pass(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1

    def test_crawl_mode_kwargs_contain_base_url(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"

    def test_crawl_mode_kwargs_no_seeds_file(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert "seeds_file" not in passes[0].kwargs

    def test_output_dir_created(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        XSSTrikeLocalTool().build_execution_passes(ctx)
        expected = tmp_path / "projects" / "testproject" / "tool_outputs" / "xsstrike"
        assert expected.exists()

    def test_label_suffix_is_repo_name(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="crawl")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].label_suffix == "testrepo"

    def test_default_empty_mode_treated_as_crawl(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
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
        repo = _make_repo(xsstrike_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert "seeds_file" in passes[0].kwargs
        assert "base_url" not in passes[0].kwargs

    def test_noir_seeds_file_contains_correct_urls(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {"/api/users": {}}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        repo = _make_repo(xsstrike_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        seeds_path = Path(passes[0].kwargs["seeds_file"])
        urls = seeds_path.read_text(encoding="utf-8").strip().splitlines()
        assert "http://localhost:8080/api/users" in urls

    def test_noir_mode_no_oas3_falls_back_to_crawl(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"
        assert "seeds_file" not in passes[0].kwargs

    def test_noir_mode_empty_oas3_paths_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        noir_dir.mkdir(parents=True)
        oas3 = {"openapi": "3.0.0", "paths": {}}
        (noir_dir / "testrepo_20240101T000000_oas3.json").write_text(json.dumps(oas3))
        repo = _make_repo(xsstrike_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
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
        repo = _make_repo(xsstrike_mode="noir")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
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
        repo = _make_repo(xsstrike_mode="provided", oas3_path=str(oas3_file))
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert "seeds_file" in passes[0].kwargs

    def test_provided_mode_seeds_url_correct(self, tmp_path: Path) -> None:
        oas3_file = tmp_path / "endpoints.json"
        oas3_file.write_text(
            json.dumps({"openapi": "3.0.0", "paths": {"/api/v1/health": {}}})
        )
        repo = _make_repo(xsstrike_mode="provided", oas3_path=str(oas3_file))
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        seeds_path = Path(passes[0].kwargs["seeds_file"])
        urls = seeds_path.read_text(encoding="utf-8").strip().splitlines()
        assert "http://localhost:8080/api/v1/health" in urls

    def test_provided_mode_empty_oas3_path_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(xsstrike_mode="provided", oas3_path="")
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("base_url") == "http://localhost:8080"

    def test_provided_mode_missing_oas3_file_falls_back_to_crawl(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(
            xsstrike_mode="provided",
            oas3_path=str(tmp_path / "nonexistent.json"),
        )
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
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


# ---------------------------------------------------------------------------
# build_command — crawl level
# ---------------------------------------------------------------------------


class TestBuildCommandCrawlLevel:
    def test_default_crawl_level_is_10(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "-l" in cmd
        idx = cmd.index("-l")
        assert cmd[idx + 1] == "10"

    def test_custom_crawl_level_passed_through(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(
            base_url="http://localhost:8080", log_file=log, crawl_level=5
        )
        idx = cmd.index("-l")
        assert cmd[idx + 1] == "5"

    def test_crawl_level_from_repo_config_used(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_crawl_level=7)
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("crawl_level") == 7


# ---------------------------------------------------------------------------
# build_command — headers
# ---------------------------------------------------------------------------


class TestBuildCommandHeaders:
    def test_no_headers_kwarg_omits_headers_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--headers" not in cmd

    def test_headers_kwarg_adds_headers_flag(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        headers = {"Cookie": "session=abc123"}
        cmd = tool.build_command(
            base_url="http://localhost:8080", log_file=log, headers=headers
        )
        assert "--headers" in cmd

    def test_headers_value_is_json_serialised(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        headers = {"Cookie": "session=abc123", "X-Forwarded-For": "127.0.0.1"}
        cmd = tool.build_command(
            base_url="http://localhost:8080", log_file=log, headers=headers
        )
        idx = cmd.index("--headers")
        parsed = json.loads(cmd[idx + 1])
        assert parsed == headers

    def test_repo_xsstrike_headers_passed_to_kwargs(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_headers={"Cookie": "PHPSESSID=xyz"})
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs.get("headers") == {"Cookie": "PHPSESSID=xyz"}

    def test_repo_empty_xsstrike_headers_not_in_kwargs(self, tmp_path: Path) -> None:
        repo = _make_repo(xsstrike_headers={})
        ctx = _make_context(repo, str(tmp_path))
        passes = XSSTrikeLocalTool().build_execution_passes(ctx)
        assert "headers" not in passes[0].kwargs


# ---------------------------------------------------------------------------
# build_command — scan-enhancing flags (--path, -e, -t, --timeout)
# ---------------------------------------------------------------------------


class TestBuildCommandScanFlags:
    def test_path_flag_present(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--path" in cmd

    def test_encode_flag_present(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "-e" in cmd

    def test_threads_flag_present(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "-t" in cmd

    def test_threads_value_in_safe_range(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        idx = cmd.index("-t")
        thread_count = int(cmd[idx + 1])
        assert 2 <= thread_count <= 8

    def test_timeout_flag_present(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        assert "--timeout" in cmd

    def test_timeout_value_is_15(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        idx = cmd.index("--timeout")
        assert cmd[idx + 1] == "15"

    def test_new_flags_present_in_seeds_mode(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        seeds = str(tmp_path / "seeds.txt")
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(seeds_file=seeds, log_file=log)
        assert "--path" in cmd
        assert "-e" in cmd
        assert "-t" in cmd
        assert "--timeout" in cmd

    def test_threads_value_equals_recommended(self, tmp_path: Path) -> None:
        tool = XSSTrikeLocalTool()
        log = str(tmp_path / "out.log")
        cmd = tool.build_command(base_url="http://localhost:8080", log_file=log)
        idx = cmd.index("-t")
        assert int(cmd[idx + 1]) == _recommended_thread_count()


# ---------------------------------------------------------------------------
# _recommended_thread_count — floor / cap behaviour
# ---------------------------------------------------------------------------


class TestRecommendedThreadCount:
    def test_none_cpu_count_returns_two(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.local.xsstrike.os.cpu_count",
            return_value=None,
        ):
            assert _recommended_thread_count() == 2

    def test_single_cpu_floors_to_two(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.local.xsstrike.os.cpu_count", return_value=1
        ):
            assert _recommended_thread_count() == 2

    def test_four_cpus_returns_four(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.local.xsstrike.os.cpu_count", return_value=4
        ):
            assert _recommended_thread_count() == 4

    def test_high_cpu_count_caps_at_eight(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.local.xsstrike.os.cpu_count", return_value=32
        ):
            assert _recommended_thread_count() == 8

    def test_exactly_eight_cpus_returns_eight(self) -> None:
        with patch(
            "infrastructure.tools.wrappers.local.xsstrike.os.cpu_count", return_value=8
        ):
            assert _recommended_thread_count() == 8
