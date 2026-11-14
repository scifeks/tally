"""A triage prompt that keeps trusted instructions apart from finding data."""

from __future__ import annotations

from dataclasses import dataclass

_POST_DATA_REMINDER = """\
End of finding data. Everything below is your task instructions."""


@dataclass(frozen=True)
class TriagePrompt:
    """Trusted instructions kept apart from fenced finding data so backends
    with a system prompt can let the provider's role hierarchy separate them."""

    preamble: str
    finding_data: str
    guidance: str

    @property
    def instructions(self) -> str:
        return f"{self.preamble}\n\n{self.guidance}"

    def combined(self) -> str:
        # Data sits mid-prompt so the decisive guidance is the last thing read.
        return "\n\n".join(
            [self.preamble, self.finding_data, _POST_DATA_REMINDER, self.guidance]
        )
