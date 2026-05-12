"""REPL adapter: writes progress lines straight to stdout."""

from __future__ import annotations

import re
import sys

_COUNTER_TAIL = re.compile(r"\d[\d/]*\s*$")


class StdoutProgressReporter:
    """Satisfies ProgressReporter; emits to the REPL terminal."""

    def __init__(self) -> None:
        self._last_prefix: str = ""

    @staticmethod
    def _extract_prefix(message: str) -> str:
        return _COUNTER_TAIL.sub("", message)

    def report(self, message: str) -> None:
        prefix = self._extract_prefix(message)
        if prefix and prefix == self._last_prefix:
            sys.stdout.write(f"\033[A\r\033[2K{message}\n")
            sys.stdout.flush()
        else:
            print(message)
        self._last_prefix = prefix
