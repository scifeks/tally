"""CLI adapter implementations for port contracts."""

from __future__ import annotations


class CliPromptAdapter:
    """Satisfies UserPromptPort; always approves without prompting."""

    def confirm(self, question: str, *, default: bool = False) -> bool:
        del question, default
        return True

    def approve_all_remaining(self) -> None:
        return


class CliProgressReporter:
    """Satisfies ProgressReporter; prints to stdout."""

    def report(self, message: str) -> None:
        print(message)
