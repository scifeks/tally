"""Unit tests for TestDirFiltering via FindingIngestor._build_chunks."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.rag.ingestor import FindingIngestor
from core.config.schemas import Repository
from domain.tools.base import ToolResult
from tests.fixtures.ingestor_stubs import _NetworkStubBuilder, _StubBuilder


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


class TestTestDirFiltering:
    def _make_ingestor(
        self,
        rows: list[dict],
        repos: list[Repository],
        tool_name: str = "semgrep",
        network: bool = False,
    ) -> FindingIngestor:
        if network:
            builder: _StubBuilder | _NetworkStubBuilder = _NetworkStubBuilder(rows)
        else:
            builder = _StubBuilder(rows)
        rag_engine = MagicMock()
        return FindingIngestor(
            rag_engine=rag_engine,
            project_name="test",
            builders={tool_name: builder},  # type: ignore[dict-item]
            repositories=repos,
        )

    def test_excludes_file_in_test_dir(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        rows = [{"file_path": "/repos/app/tests/x.py"}]
        ingestor = self._make_ingestor(rows, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert result == []

    def test_includes_src_file(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        rows = [{"file_path": "/repos/app/src/x.py"}]
        ingestor = self._make_ingestor(rows, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1
        assert result[0][1]["file_path"] == "/src/x.py"

    def test_excludes_exact_test_dir_path(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        # rel_path would be "/tests" (no trailing file)
        rows = [{"file_path": "/repos/app/tests"}]
        ingestor = self._make_ingestor(rows, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert result == []

    def test_no_filter_when_test_dirs_empty(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=[])]
        rows = [{"file_path": "/repos/app/tests/x.py"}]
        ingestor = self._make_ingestor(rows, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1

    def test_no_filter_when_repo_not_matched(self) -> None:
        # file path doesn't start with any known repo prefix → repo_name is None
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        rows = [{"file_path": "/other/tests/x.py"}]
        ingestor = self._make_ingestor(rows, repos)
        result = ingestor._build_chunks(_tool_result(), "default")
        assert len(result) == 1

    def test_no_filter_for_non_code_domain(self) -> None:
        repos = [_repo("myapp", "/repos/app", test_dirs=["tests"])]
        rows = [{"file_path": "/repos/app/tests/x.py"}]
        ingestor = self._make_ingestor(rows, repos, tool_name="nmap", network=True)
        result = ingestor._build_chunks(_tool_result("nmap"), "default")
        # network domain — no path filtering applied
        assert len(result) == 1
