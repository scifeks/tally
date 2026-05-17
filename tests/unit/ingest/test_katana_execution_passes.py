"""Unit tests for KatanaLocalTool.build_execution_passes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from domain.tools.execution_config import ToolExecutionConfig
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.katana import KatanaLocalTool


class _NullConverter:
    def convert(self, source, output_dir):
        raise AssertionError("not used in this test")


_CONVERTER = _NullConverter()


def _make_repo(
    base_urls: list[str] | None = None,
    katana_depth: int = 3,
    katana_headless: bool = False,
    katana_headers: dict[str, str] | None = None,
) -> Repository:
    return Repository.model_construct(
        name="testrepo",
        type=["api"],
        path="/repo",
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=base_urls if base_urls is not None else ["http://localhost:8080"],
        test_dirs=[],
        ignore_dirs=[],
        oas3_path="",
        katana_depth=katana_depth,
        katana_headless=katana_headless,
        katana_headers=katana_headers or {},
    )


def _make_context(repo: Repository, base_path: str) -> ExecutionContext:
    registry = MagicMock()
    return ExecutionContext(
        project_name="testproject",
        base_path=base_path,
        repo=repo,
        tool_config=ToolExecutionConfig(noir_provider=None),
        registry=registry,
        is_docker=False,
    )


# build_execution_passes: basic


class TestBuildExecutionPasses:
    def test_returns_one_pass(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert len(passes) == 1

    def test_label_suffix_is_repo_name(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].label_suffix == "testrepo"

    def test_output_dir_created(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(ctx)
        expected = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        assert expected.exists()

    def test_base_url_from_first_entry(self, tmp_path: Path) -> None:
        repo = _make_repo(base_urls=["http://first:8080", "http://second:9090"])
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].kwargs["base_url"] == "http://first:8080"

    def test_output_file_is_jsonl(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        output_file = str(passes[0].kwargs["output_file"])
        assert output_file.endswith(".jsonl")

    def test_output_file_contains_repo_name(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        output_file = str(passes[0].kwargs["output_file"])
        assert "testrepo" in output_file

    def test_oas3_target_is_json(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        oas3_target = str(passes[0].kwargs["oas3_target"])
        assert oas3_target.endswith("_oas3.json")

    def test_oas3_target_contains_repo_name(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        oas3_target = str(passes[0].kwargs["oas3_target"])
        assert "testrepo" in oas3_target

    def test_depth_from_repo_config(self, tmp_path: Path) -> None:
        repo = _make_repo(katana_depth=5)
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].kwargs["depth"] == 5

    def test_headless_from_repo_config_true(self, tmp_path: Path) -> None:
        repo = _make_repo(katana_headless=True)
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].kwargs["headless"] is True

    def test_headless_from_repo_config_false(self, tmp_path: Path) -> None:
        repo = _make_repo(katana_headless=False)
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].kwargs["headless"] is False

    def test_headers_included_when_set(self, tmp_path: Path) -> None:
        repo = _make_repo(katana_headers={"Cookie": "session=abc"})
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes[0].kwargs.get("headers") == {"Cookie": "session=abc"}

    def test_headers_omitted_when_empty(self, tmp_path: Path) -> None:
        repo = _make_repo(katana_headers={})
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert "headers" not in passes[0].kwargs


# build_execution_passes: no base_urls


class TestBuildExecutionPassesNoBaseUrls:
    def test_empty_base_urls_returns_no_passes(self, tmp_path: Path) -> None:
        repo = _make_repo(base_urls=[])
        ctx = _make_context(repo, str(tmp_path))
        passes = KatanaLocalTool(endpoint_converter=_CONVERTER).build_execution_passes(
            ctx
        )
        assert passes == []
