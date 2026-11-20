"""Unit tests for the prompt composer mapping in TriageRunner."""

from __future__ import annotations

import pytest

from application.triage.prompts.output_instructions import (
    FILE_OUTPUT_INSTRUCTION,
    STDOUT_OUTPUT_INSTRUCTION,
)
from application.triage.runner import _PROMPT_COMPOSERS, TriageRunner
from infrastructure.agents.claude_triage_agent import ClaudeTriageAgent
from infrastructure.agents.opencode_triage_agent import OpenCodeTriageAgent
from infrastructure.anthropic.claude_sdk_triage_agent import AgentSDKTriageAgent


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
        prompt = _PROMPT_COMPOSERS[segment](
            {"id": 1}, project="demo", output_instruction=STDOUT_OUTPUT_INSTRUCTION
        )
        assert scanner_kind in prompt.instructions


def _runner_with_backend(backend: object) -> TriageRunner:
    runner = object.__new__(TriageRunner)
    setattr(runner, "_triage_backend", backend)
    return runner


class _FileBackendStub:
    OUTPUT_INSTRUCTION = FILE_OUTPUT_INSTRUCTION


class TestOutputInstructionLookup:
    def test_runner_composes_prompt_with_backend_instruction(self) -> None:
        instruction = _runner_with_backend(_FileBackendStub())._output_instruction()
        prompt = _PROMPT_COMPOSERS["sast"](
            {"id": 1}, project="demo", output_instruction=instruction
        )
        assert FILE_OUTPUT_INSTRUCTION in prompt.instructions
        assert STDOUT_OUTPUT_INSTRUCTION not in prompt.instructions

    def test_backend_without_attribute_falls_back_to_stdout(self) -> None:
        runner = _runner_with_backend(object())
        assert runner._output_instruction() == STDOUT_OUTPUT_INSTRUCTION

    @pytest.mark.parametrize(
        ("adapter", "expected"),
        [
            pytest.param(ClaudeTriageAgent, STDOUT_OUTPUT_INSTRUCTION, id="claude"),
            pytest.param(OpenCodeTriageAgent, FILE_OUTPUT_INSTRUCTION, id="opencode"),
            pytest.param(AgentSDKTriageAgent, STDOUT_OUTPUT_INSTRUCTION, id="sdk"),
        ],
    )
    def test_output_instruction_resolves_from_adapter_classes(
        self, adapter: type, expected: str
    ) -> None:
        # Skips __init__; getattr must resolve through the class, not the instance.
        backend = object.__new__(adapter)
        assert _runner_with_backend(backend)._output_instruction() == expected
