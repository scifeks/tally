"""Unit tests for the instructions/data split in TriagePrompt."""

from __future__ import annotations

from application.triage.prompts.triage_prompt import TriagePrompt

_PROMPT = TriagePrompt(
    preamble="PREAMBLE", finding_data="FINDING_DATA", guidance="GUIDANCE"
)


def test_instructions_carry_all_trusted_text_and_no_data() -> None:
    assert "PREAMBLE" in _PROMPT.instructions
    assert "GUIDANCE" in _PROMPT.instructions
    assert "FINDING_DATA" not in _PROMPT.instructions


def test_combined_places_data_between_preamble_and_guidance() -> None:
    combined = _PROMPT.combined()
    preamble = combined.index("PREAMBLE")
    data = combined.index("FINDING_DATA")
    reminder = combined.index("End of finding data")
    guidance = combined.index("GUIDANCE")
    assert preamble < data < reminder < guidance
