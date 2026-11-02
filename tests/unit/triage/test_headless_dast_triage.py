"""Unit tests for headless triage DAST wiring."""

from __future__ import annotations

from application.triage.prompts.output_instructions import STDOUT_OUTPUT_INSTRUCTION
from application.triage.runner import _PROMPT_COMPOSERS


class TestHeadlessDastTriage:
    def test_web_composer_produces_dast_prompt(self) -> None:
        compose_fn = _PROMPT_COMPOSERS["web"]
        prompt = compose_fn(
            {"id": 99, "tool": "zap"},
            project="demo",
            output_instruction=STDOUT_OUTPUT_INSTRUCTION,
        )
        assert "vulnerable code path" in prompt.instructions.lower()
        assert "source tree" in prompt.instructions.lower()
