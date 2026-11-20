"""Detect whether a Claude Code OAuth session or setup-token is present."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class OAuthDetection:
    available: bool
    reason: str


_PROBE_TIMEOUT_SECONDS = 5.0


def detect_oauth_session() -> OAuthDetection:
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()
    if token:
        return OAuthDetection(available=True, reason="CLAUDE_CODE_OAUTH_TOKEN is set")

    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return OAuthDetection(available=False, reason="claude binary not found on PATH")
    except subprocess.TimeoutExpired:
        return OAuthDetection(available=False, reason="claude auth status timed out")

    if result.returncode == 0:
        return OAuthDetection(
            available=True, reason="claude auth status reports logged in"
        )
    return OAuthDetection(
        available=False,
        reason="claude is not logged in; run `claude /login` or `claude setup-token`",
    )
