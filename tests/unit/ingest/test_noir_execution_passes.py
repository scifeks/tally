"""Unit tests for NoirLocalTool.build_command and build_execution_passes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.config.schemas import OllamaConfig, Repository
from core.config.schemas.global_config import GlobalConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.base.noir import _compute_noir_techs
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
    config_manager.global_config = GlobalConfig.model_construct(
        noir_provider="",
    )
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

    def test_pass_kwargs_include_techs(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "techs" in passes[0].kwargs

    def test_pass_techs_match_repo_languages(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))  # languages=["javascript/typescript"]
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        techs: list[str] = passes[0].kwargs["techs"]
        assert "js_express" in techs


# ---------------------------------------------------------------------------
# _compute_noir_techs
# ---------------------------------------------------------------------------


class TestComputeNoirTechs:
    def test_python_returns_five_techs(self) -> None:
        result = _compute_noir_techs(["python"])
        assert len(result) == 5
        assert "python_django" in result
        assert "python_flask" in result

    def test_python_and_js_combined_no_duplicates(self) -> None:
        result = _compute_noir_techs(["python", "javascript/typescript"])
        assert len(result) == len(set(result))
        assert "python_django" in result
        assert "js_express" in result

    def test_unknown_language_returns_empty(self) -> None:
        assert _compute_noir_techs(["aiohttp"]) == []

    def test_empty_list_returns_empty(self) -> None:
        assert _compute_noir_techs([]) == []

    def test_case_insensitive(self) -> None:
        lower = _compute_noir_techs(["python"])
        upper = _compute_noir_techs(["Python"])
        assert lower == upper


# ---------------------------------------------------------------------------
# build_command with techs
# ---------------------------------------------------------------------------


class TestNoirBuildCommandTechs:
    def test_techs_appended_as_t_flag(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            techs=["python_flask", "python_django"],
        )
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "python_flask,python_django"

    def test_empty_techs_omits_t_flag(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            techs=[],
        )
        assert "-t" not in cmd

    def test_absent_techs_omits_t_flag(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
        )
        assert "-t" not in cmd

    def test_none_techs_omits_t_flag(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            techs=None,
        )
        assert "-t" not in cmd


# ---------------------------------------------------------------------------
# Exclude path prefixes
# ---------------------------------------------------------------------------


class TestExcludePathPrefixes:
    def test_pass_kwargs_include_exclude_path_prefixes(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        (src / "composer.json").write_text("{}")
        (src / "vendor").mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "exclude_path_prefixes" in passes[0].kwargs
        assert "/vendor/" in passes[0].kwargs["exclude_path_prefixes"]

    def test_pass_kwargs_no_lockfile_returns_only_git_prefix(
        self, tmp_path: Path
    ) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        (src / ".git").mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        prefixes: list[str] = passes[0].kwargs["exclude_path_prefixes"]
        assert prefixes == ["/.git/"]

    def test_pass_kwargs_empty_repo_no_prefixes(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert passes[0].kwargs["exclude_path_prefixes"] == []

    def test_exclude_prefixes_stored_after_build_command(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            exclude_path_prefixes=["/vendor/", "/node_modules/"],
        )
        assert tool._exclude_path_prefixes == ["/vendor/", "/node_modules/"]

    def test_exclude_prefixes_not_in_cli_args(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            exclude_path_prefixes=["/vendor/"],
        )
        assert "/vendor/" not in cmd
        assert "exclude_path_prefixes" not in " ".join(cmd)

    def test_exclude_prefixes_cleared_after_parse_output(self, tmp_path: Path) -> None:
        report = tmp_path / "report.json"
        report.write_text(json.dumps({"openapi": "3.0.0", "paths": {}}))
        tool = NoirLocalTool()
        tool._last_report_path = report
        tool._exclude_path_prefixes = ["/vendor/"]
        tool.parse_output("", {})
        assert tool._exclude_path_prefixes == []

    def test_parse_output_filters_dynamic_prefix(self, tmp_path: Path) -> None:
        oas3 = {
            "openapi": "3.0.0",
            "paths": {
                "/api/users": {"get": {}},
                "/node_modules/react/index": {"get": {}},
            },
        }
        report = tmp_path / "report.json"
        report.write_text(json.dumps(oas3))
        tool = NoirLocalTool()
        tool._last_report_path = report
        tool._exclude_path_prefixes = ["/node_modules/"]
        parsed = tool.parse_output("", {})
        assert len(parsed["endpoints"]) == 1
        assert parsed["endpoints"][0]["path"] == "/api/users"
        assert parsed["summary"]["total_endpoints"] == 1

    def test_parse_output_filters_static_fallback(self, tmp_path: Path) -> None:
        """Static vendor indicators still catch exclusions when no dynamic prefix."""
        oas3 = {
            "openapi": "3.0.0",
            "paths": {
                "/api/users": {"get": {}},
                "/vendor/package/route": {"get": {}},
            },
        }
        report = tmp_path / "report.json"
        report.write_text(json.dumps(oas3))
        tool = NoirLocalTool()
        tool._last_report_path = report
        # No dynamic prefixes — fallback to static list
        tool._exclude_path_prefixes = []
        parsed = tool.parse_output("", {})
        assert len(parsed["endpoints"]) == 1
        assert parsed["endpoints"][0]["path"] == "/api/users"

    def test_count_findings_matches_filtered_endpoint_count(
        self, tmp_path: Path
    ) -> None:
        oas3 = {
            "openapi": "3.0.0",
            "paths": {
                "/api/a": {"get": {}},
                "/api/b": {"post": {}},
                "/vendor/x": {"get": {}},
            },
        }
        report = tmp_path / "report.json"
        report.write_text(json.dumps(oas3))
        tool = NoirLocalTool()
        tool._last_report_path = report
        tool._exclude_path_prefixes = ["/vendor/"]
        parsed = tool.parse_output("", {})
        assert tool.count_findings(parsed) == len(parsed["endpoints"]) == 2


# ---------------------------------------------------------------------------
# AI flags in build_command
# ---------------------------------------------------------------------------


class TestNoirAiFlags:
    def test_ai_flags_appended_when_both_present(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            ai_provider_url="http://localhost:11434",
            ai_model="gemma3:27b",
        )
        assert "--ai-provider" in cmd
        assert "http://localhost:11434" in cmd
        assert "--ai-model" in cmd
        assert "gemma3:27b" in cmd

    def test_ai_flags_omitted_when_absent(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
        )
        assert "--ai-provider" not in cmd
        assert "--ai-model" not in cmd

    def test_ai_flags_omitted_when_provider_empty(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            ai_provider_url="",
            ai_model="gemma3:27b",
        )
        assert "--ai-provider" not in cmd
        assert "--ai-model" not in cmd

    def test_ai_flags_omitted_when_model_empty(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            ai_provider_url="http://localhost:11434",
            ai_model="",
        )
        assert "--ai-provider" not in cmd
        assert "--ai-model" not in cmd

    def test_ai_max_token_appended_when_set(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            ai_provider_url="http://localhost:11434",
            ai_model="gemma3:27b",
            ai_max_token=8192,
        )
        assert "--ai-max-token" in cmd
        assert "8192" in cmd

    def test_ai_max_token_omitted_when_absent(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        tool = NoirLocalTool()
        cmd = tool.build_command(
            source_path=str(src),
            output_file=str(tmp_path / "out.json"),
            ai_provider_url="http://localhost:11434",
            ai_model="gemma3:27b",
        )
        assert "--ai-max-token" not in cmd


# ---------------------------------------------------------------------------
# AI config resolution in build_execution_passes
# ---------------------------------------------------------------------------


def _make_global_config(
    noir_provider: str = "",
    ollama_noir: OllamaConfig | None = None,
) -> GlobalConfig:
    return GlobalConfig.model_construct(
        noir_provider=noir_provider,
        ollama_noir=ollama_noir,
    )


class TestNoirExecutionPassesAiConfig:
    def test_ai_kwargs_present_when_noir_provider_set(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        ollama_noir = OllamaConfig(
            base_url="http://10.0.0.1:11434",
            model="gemma3:27b",
            num_ctx=8192,
        )
        ctx.config_manager.global_config = _make_global_config(
            noir_provider="ollama_noir",
            ollama_noir=ollama_noir,
        )
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        kw = passes[0].kwargs
        assert kw.get("ai_provider_url") == "ollama"
        assert kw.get("ai_model") == "gemma3:27b"
        assert kw.get("ai_max_token") == 8192
        assert passes[0].env == {"OLLAMA_HOST": "http://10.0.0.1:11434"}

    def test_ai_max_token_absent_when_num_ctx_none(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        ollama_noir = OllamaConfig(
            base_url="http://10.0.0.1:11434",
            model="gemma3:27b",
            num_ctx=None,
        )
        ctx.config_manager.global_config = _make_global_config(
            noir_provider="ollama_noir",
            ollama_noir=ollama_noir,
        )
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "ai_max_token" not in passes[0].kwargs
        assert passes[0].env == {"OLLAMA_HOST": "http://10.0.0.1:11434"}

    def test_ai_kwargs_absent_when_noir_provider_empty(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        ctx.config_manager.global_config = _make_global_config(
            noir_provider="",
        )
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "ai_provider_url" not in passes[0].kwargs
        assert "ai_model" not in passes[0].kwargs
        assert passes[0].env is None

    def test_ai_kwargs_absent_when_provider_name_invalid(self, tmp_path: Path) -> None:
        src = tmp_path / "repo"
        src.mkdir()
        repo = _make_repo(str(src))
        ctx = _make_context(repo, str(tmp_path))
        ctx.config_manager.global_config = _make_global_config(
            noir_provider="nonexistent_provider",
        )
        tool = NoirLocalTool()
        passes = tool.build_execution_passes(ctx)
        assert "ai_provider_url" not in passes[0].kwargs
        assert "ai_model" not in passes[0].kwargs
