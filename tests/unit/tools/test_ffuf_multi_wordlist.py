"""Unit tests for ffuf multi-wordlist execution and merging."""

from unittest.mock import MagicMock, patch

from domain.tools.base import ToolResult
from infrastructure.tools.wrappers.base.ffuf import BaseFFufTool, resolve_wordlists


class TestResolveWordlists:
    """resolve_wordlists returns valid paths in priority order."""

    @patch("pathlib.Path.exists", return_value=True)
    def test_returns_all_valid_configured_paths(self, _exists):
        result = resolve_wordlists(["/a.txt", "/b.txt"])
        assert result == ["/a.txt", "/b.txt"]

    @patch("pathlib.Path.exists", return_value=False)
    def test_returns_empty_when_nothing_found(self, _exists):
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_wordlists([])
        assert result == []

    def test_empty_config_falls_back(self):
        result = resolve_wordlists([])
        assert isinstance(result, list)


class TestMultiPassExecution:
    """build_execution_passes creates one pass per wordlist."""

    def _make_context(self, wordlist_paths):
        ctx = MagicMock()
        ctx.repo.name = "test-repo"
        ctx.service.base_urls = ["http://localhost:8080"]
        ctx.base_path = "/tmp/tally"
        ctx.project_name = "test-project"
        ctx.tool_config.ffuf_wordlist_paths = wordlist_paths
        return ctx

    @patch(
        "infrastructure.tools.wrappers.base.ffuf.resolve_wordlists",
        return_value=["/a.txt", "/b.txt", "/c.txt"],
    )
    @patch.object(BaseFFufTool, "_get_output_file")
    def test_creates_one_pass_per_wordlist(self, mock_output, mock_resolve):
        mock_output.side_effect = [
            "/out/1.json",
            "/out/2.json",
            "/out/3.json",
        ]
        tool = BaseFFufTool()
        ctx = self._make_context(["/a.txt", "/b.txt", "/c.txt"])
        passes = tool.build_execution_passes(ctx)
        assert len(passes) == 3

    @patch(
        "infrastructure.tools.wrappers.base.ffuf.resolve_wordlists",
        return_value=["/a.txt", "/b.txt"],
    )
    @patch.object(BaseFFufTool, "_get_output_file")
    def test_passes_have_unique_labels(self, mock_output, mock_resolve):
        mock_output.side_effect = ["/out/1.json", "/out/2.json"]
        tool = BaseFFufTool()
        ctx = self._make_context(["/a.txt", "/b.txt"])
        passes = tool.build_execution_passes(ctx)
        labels = [p.label_suffix for p in passes]
        assert len(set(labels)) == len(labels)

    @patch(
        "infrastructure.tools.wrappers.base.ffuf.resolve_wordlists",
        return_value=[],
    )
    def test_returns_empty_when_no_wordlists(self, _resolve):
        tool = BaseFFufTool()
        ctx = self._make_context([])
        passes = tool.build_execution_passes(ctx)
        assert passes == []


class TestMergePassResults:
    """merge_pass_results combines findings from multiple passes."""

    def _make_result(self, findings, duration=1.0):
        return ToolResult(
            tool_name="ffuf",
            success=True,
            output="",
            parsed_data={
                "findings": findings,
                "summary": {"total_findings": len(findings)},
            },
            output_files={},
            timestamp="2025-01-01T00:00:00",
            duration_seconds=duration,
        )

    def test_merges_findings_from_multiple_passes(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/b", "status": 200}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 2

    def test_deduplicates_by_url_and_status(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/a", "status": 200}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 1

    def test_keeps_different_status_same_url(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        r2 = self._make_result([{"url": "http://x/a", "status": 403}])
        merged = tool.merge_pass_results([r1, r2])
        assert merged.parsed_data is not None
        assert len(merged.parsed_data["findings"]) == 2

    def test_sums_duration(self):
        tool = BaseFFufTool()
        r1 = self._make_result([], duration=2.5)
        r2 = self._make_result([], duration=3.5)
        merged = tool.merge_pass_results([r1, r2])
        assert merged.duration_seconds == 6.0

    def test_single_pass_returns_as_is(self):
        tool = BaseFFufTool()
        r1 = self._make_result([{"url": "http://x/a", "status": 200}])
        merged = tool.merge_pass_results([r1])
        assert merged is r1
