"""Unit tests for the prompt composer mapping in TriageRunner."""

from __future__ import annotations

import pytest

from application.triage.runner import _PROMPT_COMPOSERS


class TestPromptComposers:
    @pytest.mark.parametrize(
        ("segment", "scanner_kind"),
        [
            pytest.param("sast", "semgrep finding", id="sast"),
            pytest.param("web", "DAST finding", id="web"),
        ],
    )
    def test_segment_gets_prompt_for_its_scanner_kind(
        self, segment: str, scanner_kind: str
    ) -> None:
        prompt = _PROMPT_COMPOSERS[segment]({"id": 1}, project="demo")
        assert scanner_kind in prompt.instructions
