"""Unit tests for DalFox katana seeds helpers and katana/auto modes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.dalfox import (
    DalFoxLocalTool,
    _build_seeds_from_katana,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    name: str = "testrepo",
    base_urls: list[str] | None = None,
    dalfox_mode: str = "noir",
    dalfox_headers: dict[str, str] | None = None,
    node_app: bool = False,
    oas3_path: str = "",
) -> Repository:
    return Repository.model_construct(
        name=name,
        type=["api"],
        path="/repo",
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=base_urls if base_urls is not None else ["http://localhost:8080"],
        test_dirs=[],
        ignore_dirs=[],
        oas3_path=oas3_path,
        node_app=node_app,
        xsstrike_mode="crawl",
        xsstrike_crawl_level=10,
        xsstrike_headers={},
        dalfox_mode=dalfox_mode,
        dalfox_headers=dalfox_headers or {},
        katana_headless=False,
        katana_depth=3,
        katana_headers={},
    )


def _make_context(repo: Repository, base_path: str) -> ExecutionContext:
    return ExecutionContext(
        project_name="testproject",
        base_path=base_path,
        repo=repo,
        config_manager=MagicMock(),
        registry=MagicMock(),
        is_docker=False,
    )


def _write_katana_oas3(katana_dir: Path, repo_name: str, paths: list[str]) -> Path:
    katana_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "test", "version": "1.0.0"},
        "paths": {p: {} for p in paths},
    }
    f = katana_dir / f"{repo_name}_20260101T000000_oas3.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    return f


def _write_noir_oas3(noir_dir: Path, repo_name: str, paths: list[str]) -> Path:
    noir_dir.mkdir(parents=True, exist_ok=True)
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "test", "version": "1.0.0"},
        "paths": {p: {} for p in paths},
    }
    f = noir_dir / f"{repo_name}_20260101T000000_oas3.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _build_seeds_from_katana — unit tests
# ---------------------------------------------------------------------------


class TestBuildSeedsFromKatana:
    def test_happy_path_returns_seeds_file(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        _write_katana_oas3(katana_dir, "repo", ["/api/users"])
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            out_dir,
            "ts",
        )
        assert result is not None
        assert Path(result).exists()

    def test_seeds_contain_full_urls(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        _write_katana_oas3(katana_dir, "repo", ["/api/items"])
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            out_dir,
            "ts",
        )
        assert result is not None
        assert "http://localhost:8080/api/items" in Path(result).read_text()

    def test_missing_dir_returns_none(self, tmp_path: Path) -> None:
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            tmp_path / "out",
            "ts",
        )
        assert result is None

    def test_no_matching_files_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            tmp_path / "out",
            "ts",
        )
        assert result is None

    def test_empty_paths_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        _write_katana_oas3(katana_dir, "repo", [])
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            tmp_path / "out",
            "ts",
        )
        assert result is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        (katana_dir / "repo_20260101T000000_oas3.json").write_text(
            "not json", encoding="utf-8"
        )
        result = _build_seeds_from_katana(
            str(tmp_path),
            "proj",
            "repo",
            "http://localhost:8080",
            tmp_path / "out",
            "ts",
        )
        assert result is None


# ---------------------------------------------------------------------------
# build_execution_passes — katana mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesKatanaMode:
    def test_katana_mode_uses_seeds_file(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        _write_katana_oas3(katana_dir, "testrepo", ["/api/v1"])
        repo = _make_repo(dalfox_mode="katana")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert "seeds_file" in passes[0].kwargs

    def test_katana_mode_no_katana_output_skips(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="katana")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes == []


# ---------------------------------------------------------------------------
# build_execution_passes — auto mode
# ---------------------------------------------------------------------------


class TestBuildExecutionPassesAutoMode:
    def test_auto_prefers_katana_when_both_exist(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        _write_katana_oas3(katana_dir, "testrepo", ["/katana-path"])
        _write_noir_oas3(noir_dir, "testrepo", ["/noir-path"])
        repo = _make_repo(dalfox_mode="auto")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        seeds = Path(passes[0].kwargs["seeds_file"]).read_text()
        assert "/katana-path" in seeds
        assert "/noir-path" not in seeds

    def test_auto_falls_back_to_noir_when_katana_absent(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        _write_noir_oas3(noir_dir, "testrepo", ["/noir-path"])
        repo = _make_repo(dalfox_mode="auto")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        seeds = Path(passes[0].kwargs["seeds_file"]).read_text()
        assert "/noir-path" in seeds

    def test_auto_skips_when_both_absent(self, tmp_path: Path) -> None:
        repo = _make_repo(dalfox_mode="auto")
        ctx = _make_context(repo, str(tmp_path))
        passes = DalFoxLocalTool().build_execution_passes(ctx)
        assert passes == []
