"""Unit tests for FindingIngestor path normalisation helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.config.schemas import Repository  # noqa: E402
from core.rag.ingestor import (  # noqa: E402
    FindingIngestor,
    _normalize_path,
)
from core.tools.base import ToolResult  # noqa: E402

# ---------------------------------------------------------------------------
# Repository stub factory (bypasses path-existence validator)
# ---------------------------------------------------------------------------


def _repo(name: str, path: str) -> Repository:
    return Repository.model_construct(
        name=name,
        path=path,
        type=["library"],
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
    )


# ---------------------------------------------------------------------------
# _normalize_path tests
# ---------------------------------------------------------------------------


class TestNormalizePath:
    def test_normalize_strips_prefix(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("/repos/app/src/main.py", repos)
        assert rel == "/src/main.py"
        assert repo_name == "myapp"

    def test_normalize_no_match_returns_original(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("/other/path/file.py", repos)
        assert rel == "/other/path/file.py"
        assert repo_name is None

    def test_normalize_empty_path_returns_empty(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, repo_name = _normalize_path("", repos)
        assert rel == ""
        assert repo_name is None

    def test_normalize_repo_path_with_trailing_slash(self) -> None:
        repos = [_repo("myapp", "/repos/app/")]
        rel, repo_name = _normalize_path("/repos/app/src/main.py", repos)
        assert rel == "/src/main.py"
        assert repo_name == "myapp"
        assert not rel.startswith("//")

    def test_normalize_leading_slash_present(self) -> None:
        repos = [_repo("myapp", "/repos/app")]
        rel, _ = _normalize_path("/repos/app/foo/bar/baz.php", repos)
        assert rel.startswith("/")

    def test_normalize_empty_repo_list(self) -> None:
        rel, repo_name = _normalize_path("/some/file.py", [])
        assert rel == "/some/file.py"
        assert repo_name is None


# ---------------------------------------------------------------------------
# Stub ChunkBuilder
# ---------------------------------------------------------------------------


class _StubBuilder:
    tool_name = "semgrep"
    domain = "code"
    segment = "sast"
    non_enriched_fields: frozenset[str] = frozenset()
    type_flags: dict[str, set[str]] = {}
    should_enrich = False

    def __init__(
        self, chunks: list[tuple[str, dict[str, Any], str]] | None = None
    ) -> None:
        self._chunks = chunks or []

    def build(
        self, result: ToolResult, profile: str
    ) -> list[tuple[str, dict[str, Any], str]]:
        return list(self._chunks)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return str(finding)


def _tool_result(tool_name: str = "semgrep") -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output="",
        parsed_data={},
        output_files={},
        timestamp="2026-01-01T00:00:00",
        duration_seconds=0.0,
    )


# ---------------------------------------------------------------------------
# FindingIngestor._build_chunks tests
# ---------------------------------------------------------------------------


class TestBuildChunks:
    def _make_ingestor(
        self,
        chunks: list[tuple[str, dict[str, Any], str]],
        repos: list[Repository] | None,
    ) -> FindingIngestor:
        builder = _StubBuilder(chunks)
        rag_engine = MagicMock()
        return FindingIngestor(
            rag_engine=rag_engine,
            project_name="test",
            builders={"semgrep": builder},  # type: ignore[dict-item]
            repositories=repos,
        )

    def test_build_chunks_sets_relative_file_path(self) -> None:
        chunks = [("text", {"file_path": "/repos/app/src/main.py"}, "id1")]
        repos = [_repo("myapp", "/repos/app")]
        ingestor = self._make_ingestor(chunks, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1
        meta = result[0][1]
        assert meta["file_path"] == "/src/main.py"
        assert "/repos/app" not in meta["file_path"]

    def test_build_chunks_sets_repo_in_metadata(self) -> None:
        chunks = [("text", {"file_path": "/repos/app/src/main.py"}, "id1")]
        repos = [_repo("myapp", "/repos/app")]
        ingestor = self._make_ingestor(chunks, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert result[0][1]["repo"] == "myapp"

    def test_build_chunks_excludes_code_chunk_with_no_file(self) -> None:
        chunks = [("text", {"file_path": ""}, "id1")]
        repos = [_repo("myapp", "/repos/app")]
        ingestor = self._make_ingestor(chunks, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert result == []

    def test_build_chunks_skips_normalization_when_repos_none(self) -> None:
        chunks = [
            ("text", {"file_path": "/repos/app/src/main.py"}, "id1"),
        ]
        ingestor = self._make_ingestor(chunks, repos=None)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1
        assert result[0][1]["file_path"] == "/repos/app/src/main.py"

    def test_build_chunks_no_match_preserves_original_path(self) -> None:
        chunks = [("text", {"file_path": "/other/path/file.py"}, "id1")]
        repos = [_repo("myapp", "/repos/app")]
        ingestor = self._make_ingestor(chunks, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1
        assert result[0][1]["file_path"] == "/other/path/file.py"
        assert result[0][1].get("repo") is None
