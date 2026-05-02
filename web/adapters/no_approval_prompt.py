"""API adapter: auto-approves all confirmations (no stdin in API context)."""

from __future__ import annotations


class NoApprovalPromptAdapter:
    """Satisfies UserPromptPort; always returns True without prompting."""

    def confirm(self, question: str, *, default: bool = False) -> bool:
        del question, default
        return True

    def approve_all_remaining(self) -> None:
        return
