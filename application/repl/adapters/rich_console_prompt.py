"""REPL adapter: reads y/N confirmations from stdin via Rich console."""

from __future__ import annotations


class RichConsolePromptAdapter:
    """Satisfies UserPromptPort; carries auto-approve state for scan sessions."""

    def __init__(self, auto_approve: bool = False) -> None:
        self._auto_approve = auto_approve

    def confirm(self, question: str, *, default: bool = False) -> bool:
        if self._auto_approve:
            return True
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            answer = input(f"{question} {suffix}: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not answer:
            return default
        return answer in ("y", "yes")

    def approve_all_remaining(self) -> None:
        if self._auto_approve:
            return
        try:
            answer = input("    Approve all remaining? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if answer in ("y", "yes"):
            self._auto_approve = True
