"""Report which background-mode credentials are available.

Interactive mode is always available (the user can always launch Claude Code).
The two background sub-paths depend on whether an OAuth session or an API key
is present. The result is informational for the UI and CLI; it does not change
Tally's behavior on its own.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from infrastructure.anthropic.oauth_detection import (
    OAuthDetection,
    detect_oauth_session,
)


@dataclass(frozen=True)
class BackgroundModeAvailability:
    oauth_available: bool
    api_key_available: bool
    interactive_available: bool
    oauth_reason: str | None = None
    api_key_reason: str | None = None


class BackgroundModeAvailabilityService:
    def __init__(
        self,
        config,
        detect_oauth: Callable[[], OAuthDetection] = detect_oauth_session,
    ) -> None:
        self._config = config
        self._detect_oauth = detect_oauth

    def evaluate(self) -> BackgroundModeAvailability:
        oauth = self._detect_oauth()
        env_api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
        cfg_api_key = getattr(self._config.claude, "api_key", "") or ""
        api_key_available = bool(env_api_key or cfg_api_key)
        api_key_reason = (
            None
            if api_key_available
            else "No ANTHROPIC_API_KEY in environment or claude.api_key in config."
        )
        return BackgroundModeAvailability(
            oauth_available=oauth.available,
            api_key_available=api_key_available,
            interactive_available=True,
            oauth_reason=None if oauth.available else oauth.reason,
            api_key_reason=api_key_reason,
        )
