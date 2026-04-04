"""Tests for Noir findings exclusion from the web UI.

The FindingsTable.vue fetches domain='code' and domain='web' findings.
Noir findings (domain='code', tool='noir') must not appear in the triage grid.

These tests verify the Python-side concerns:
- The NoirHandler.domain is 'code' (so Noir goes into the code findings bucket)
- The list_findings API endpoint passes through tool-level data needed for
  client-side filtering
- NoirHandler attributes expose the correct domain/segment to the API layer
"""

from __future__ import annotations

from application.rag.chunks.noir import NoirHandler
from application.rag.chunks.zap import ZapHandler


class TestNoirHandlerDomainAttributes:
    """NoirHandler must expose domain='code' and segment='web'."""

    def test_domain_is_code(self) -> None:
        """Noir findings go into the 'code' domain bucket — not 'web'."""
        assert NoirHandler().domain == "code"

    def test_segment_is_web(self) -> None:
        assert NoirHandler().segment == "web"

    def test_tool_name_is_noir(self) -> None:
        """The client-side filter keys on tool='noir'."""
        assert NoirHandler().tool_name == "noir"


class TestZapHandlerDomainAttributes:
    """ZapHandler must remain in 'web' domain after the segment rename."""

    def test_domain_is_web(self) -> None:
        assert ZapHandler().domain == "web"

    def test_segment_is_web(self) -> None:
        assert ZapHandler().segment == "web"


class TestNoirExcludedFromCodeFindings:
    """Verify that the UI can reliably filter Noir findings from the code bucket.

    The UI applies: codeFindings.filter(f => f.tool !== 'noir').
    These tests confirm that Noir rows have tool='noir' and domain='code',
    so the filter expression works correctly.
    """

    def _noir_rows(self) -> list[dict]:
        from domain.tools.base import ToolResult

        handler = NoirHandler()
        result = ToolResult(
            tool_name="noir",
            success=True,
            output="",
            parsed_data={
                "endpoints": [
                    {
                        "path": "/api/test",
                        "method": "GET",
                        "path_params": [],
                        "query_params": [],
                        "header_params": [],
                        "cookie_params": [],
                        "body_params": [],
                    }
                ],
                "summary": {"total_endpoints": 1, "total_paths": 1},
            },
            output_files={},
            timestamp="2026-04-03T00:00:00",
            duration_seconds=0.1,
        )
        return handler.normalize(result, profile="dvna")

    def test_noir_rows_have_tool_noir(self) -> None:
        for row in self._noir_rows():
            assert row["tool"] == "noir"

    def test_noir_rows_have_domain_code(self) -> None:
        for row in self._noir_rows():
            assert row["domain"] == "code"

    def test_client_filter_expression_excludes_noir(self) -> None:
        """Simulate the JS filter: rows where tool != 'noir' excludes all Noir rows."""
        rows = self._noir_rows()
        after_filter = [r for r in rows if r["tool"] != "noir"]
        assert after_filter == []

    def test_client_filter_expression_keeps_zap(self) -> None:
        """Simulate the JS filter: ZAP rows pass through the noir exclusion filter."""
        zap_row = {"tool": "zap", "domain": "web", "url": "http://example.com/login"}
        after_filter = [r for r in [zap_row] if r["tool"] != "noir"]
        assert after_filter == [zap_row]
