"""Unit tests for MCP triage web segment wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.mcp.service import _PROMPT_RENDERERS, McpTriageService


class TestMcpWebSegmentTriage:
    def test_prompt_renderers_includes_web(self) -> None:
        assert "web" in _PROMPT_RENDERERS

    def test_web_renderer_is_dast_trace(self) -> None:
        from application.triage.prompts import dast_trace

        assert _PROMPT_RENDERERS["web"] is dast_trace.render

    def test_fetch_batch_renders_dast_prompt_for_web(
        self,
    ) -> None:
        triage_repo = MagicMock()
        run_repo = MagicMock()
        finding_repo = MagicMock()
        tool_registry = MagicMock()

        service = McpTriageService(
            triage_repo=triage_repo,
            finding_repo=finding_repo,
            run_repo=run_repo,
            tool_registry=tool_registry,
        )

        run_repo.latest_run_id.return_value = 1

        batch = MagicMock()
        batch.id = 42
        batch.batch_data = [
            {
                "id": 99,
                "tool": "zap",
                "alert_name": "SQL Injection",
            }
        ]
        triage_repo.claim_batch.return_value = batch

        tool_obj = MagicMock()
        tool_obj.scan_segment = "web"
        tool_registry.get_tool.return_value = tool_obj

        summary = MagicMock()
        summary.total_batches = 1
        summary.counts_by_status = {}
        triage_repo.summarize_for_run.return_value = summary

        result = service.fetch_batch("demo")

        assert result["segment"] == "web"
        prompt = result["findings"][0]["prompt"]
        assert "vulnerable code path" in prompt.lower()
        assert "source tree" in prompt.lower()
