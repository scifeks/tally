"""Unit tests for headless triage DAST wiring."""

from __future__ import annotations

from application.triage.runner import _PROMPT_RENDERERS


class TestHeadlessDastTriage:
    def test_prompt_renderers_includes_web(self) -> None:
        assert "web" in _PROMPT_RENDERERS

    def test_web_renderer_is_dast_trace(self) -> None:
        from application.triage.prompts import dast_trace

        assert _PROMPT_RENDERERS["web"] is dast_trace.render

    def test_web_renderer_produces_dast_prompt(self) -> None:
        render_fn = _PROMPT_RENDERERS["web"]
        finding = {"id": 99, "tool": "zap"}
        result = render_fn(finding, project="demo")
        assert "vulnerable code path" in result.lower()
        assert "source tree" in result.lower()
