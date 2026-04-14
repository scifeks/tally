"""Unit tests for ZAP katana OAS3 resolution in build_execution_passes."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import Repository
from domain.tools.interface import ExecutionContext
from infrastructure.tools.wrappers.local.zap import ZAPLocalTool, _find_katana_oas3

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(
    name: str = "testrepo",
    base_urls: list[str] | None = None,
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
        node_app=False,
        xsstrike_mode="crawl",
        xsstrike_crawl_level=10,
        xsstrike_headers={},
        dalfox_mode="noir",
        dalfox_headers={},
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


def _write_oas3(directory: Path, repo_name: str, paths: list[str]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "test", "version": "1.0.0"},
        "paths": {p: {} for p in paths},
    }
    f = directory / f"{repo_name}_20260101T000000_oas3.json"
    f.write_text(json.dumps(spec), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# _find_katana_oas3 — unit tests
# ---------------------------------------------------------------------------


class TestFindKatanaOas3:
    def test_returns_path_when_file_exists(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        _write_oas3(katana_dir, "repo", ["/api/v1"])
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is not None
        assert "katana" in result

    def test_missing_dir_returns_none(self, tmp_path: Path) -> None:
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is None

    def test_no_matching_files_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is None

    def test_empty_paths_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        _write_oas3(katana_dir, "repo", [])
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is None

    def test_malformed_json_returns_none(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        (katana_dir / "repo_20260101T000000_oas3.json").write_text(
            "not json", encoding="utf-8"
        )
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is None

    def test_picks_most_recent_file(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "proj" / "tool_outputs" / "katana"
        katana_dir.mkdir(parents=True)
        old_spec = {
            "openapi": "3.0.3",
            "info": {"title": "t", "version": "1"},
            "paths": {"/old": {}},
        }
        new_spec = {
            "openapi": "3.0.3",
            "info": {"title": "t", "version": "1"},
            "paths": {"/new": {}},
        }
        (katana_dir / "repo_20260101T000000_oas3.json").write_text(
            json.dumps(old_spec), encoding="utf-8"
        )
        (katana_dir / "repo_20260102T000000_oas3.json").write_text(
            json.dumps(new_spec), encoding="utf-8"
        )
        result = _find_katana_oas3(str(tmp_path), "proj", "repo")
        assert result is not None
        assert "20260102" in result


# ---------------------------------------------------------------------------
# build_execution_passes — OAS3 resolution priority
# ---------------------------------------------------------------------------


class TestZapOas3Resolution:
    def test_katana_only_uses_katana_oas3(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        _write_oas3(katana_dir, "testrepo", ["/api/v1"])
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = ZAPLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert "openapi_file" in passes[0].kwargs
        assert "katana" in passes[0].kwargs["openapi_file"]

    def test_noir_only_uses_noir_oas3(self, tmp_path: Path) -> None:
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        _write_oas3(noir_dir, "testrepo", ["/api/v1"])
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = ZAPLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert "openapi_file" in passes[0].kwargs
        assert "noir" in passes[0].kwargs["openapi_file"]

    def test_both_present_prefers_katana(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        noir_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "noir"
        _write_oas3(katana_dir, "testrepo", ["/katana-path"])
        _write_oas3(noir_dir, "testrepo", ["/noir-path"])
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = ZAPLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert "katana" in passes[0].kwargs["openapi_file"]

    def test_neither_present_falls_back_to_quick_scan(self, tmp_path: Path) -> None:
        repo = _make_repo()
        ctx = _make_context(repo, str(tmp_path))
        passes = ZAPLocalTool().build_execution_passes(ctx)
        assert len(passes) == 1
        assert "openapi_file" not in passes[0].kwargs

    def test_user_oas3_path_takes_precedence_over_katana(self, tmp_path: Path) -> None:
        katana_dir = tmp_path / "projects" / "testproject" / "tool_outputs" / "katana"
        _write_oas3(katana_dir, "testrepo", ["/katana-path"])
        user_oas3 = tmp_path / "user_spec.json"
        user_oas3.write_text(
            json.dumps(
                {
                    "openapi": "3.0.3",
                    "info": {"title": "u", "version": "1"},
                    "paths": {"/user": {}},
                }
            ),
            encoding="utf-8",
        )
        repo = _make_repo(oas3_path=str(user_oas3))
        ctx = _make_context(repo, str(tmp_path))
        passes = ZAPLocalTool().build_execution_passes(ctx)
        assert passes[0].kwargs["openapi_file"] == str(user_oas3)
