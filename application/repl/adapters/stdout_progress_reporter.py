"""REPL adapter: writes progress lines straight to stdout."""

from __future__ import annotations


class StdoutProgressReporter:
    """Satisfies ProgressReporter; emits to the REPL terminal."""

    def report(self, message: str) -> None:
        print(message)
