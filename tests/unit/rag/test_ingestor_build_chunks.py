"""Unit tests for FindingIngestor._build_chunks."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from application.rag.ingestor import FindingIngestor
from core.config.schemas import Repository
from domain.tools.base import ToolResult
from tests.fixtures.ingestor_stubs import _StubBuilder


def _repo(name: str, path: str, test_dirs: list[str] | None = None) -> Repository:
    return Repository.model_construct(
        name=name,
        path=path,
        type=["library"],
        docker_path="",
        container_name="",
        languages=["python"],
        base_urls=[],
        test_dirs=test_dirs if test_dirs is not None else [],
    )


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

    def test_build_chunks_repo_name_injected_sets_repo_for_relative_path(self) -> None:
        """repo_name injection sets meta['repo'] even when file_path is relative."""
        chunks = [("text", {"file_path": "config/aws.js"}, "id1")]
        repos = [_repo("myapp", "/repos/app")]
        builder = _StubBuilder(chunks)
        ingestor = FindingIngestor(
            rag_engine=MagicMock(),
            project_name="test",
            builders={"semgrep": builder},  # type: ignore[dict-item]
            repositories=repos,
            repo_name="myapp",
        )
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1
        assert result[0][1]["repo"] == "myapp"
        # Relative path has no prefix to strip — returned as-is
        assert result[0][1]["file_path"] == "config/aws.js"
