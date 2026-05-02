"""Hexagonal port for interactive y/N confirmations.

Adapters:
  application/repl/adapters/rich_console_prompt.py  (REPL, reads stdin)
  web/adapters/no_approval_prompt.py                (API, always approves)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UserPromptPort(Protocol):
    def confirm(self, question: str, *, default: bool = False) -> bool: ...

    def approve_all_remaining(self) -> None: ...
