"""Port for interactive y/N confirmations."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class UserPromptPort(Protocol):
    def confirm(self, question: str, *, default: bool = False) -> bool: ...

    def approve_all_remaining(self) -> None: ...
