"""Credential resolution for triage agent backends."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config.schemas.claude_config import ClaudeConfig
    from core.config.schemas.opencode_config import OpenCodeConfig


class ClaudeAuthMode(Enum):
    API_KEY = "api_key"
    OAUTH = "oauth"


@dataclass(frozen=True)
class ClaudeCredentials:
    mode: ClaudeAuthMode
    api_key: str


@dataclass(frozen=True)
class OpenCodeCredentials:
    api_key: str
    api_provider: str


def resolve_claude_credentials(
    claude_config: ClaudeConfig | None,
) -> ClaudeCredentials:
    if claude_config and claude_config.api_key:
        return ClaudeCredentials(
            mode=ClaudeAuthMode.API_KEY,
            api_key=claude_config.api_key,
        )
    return ClaudeCredentials(
        mode=ClaudeAuthMode.OAUTH,
        api_key="",
    )


def resolve_opencode_credentials(
    opencode_config: OpenCodeConfig | None,
) -> OpenCodeCredentials:
    if opencode_config:
        return OpenCodeCredentials(
            api_key=opencode_config.api_key,
            api_provider=opencode_config.api_provider,
        )
    return OpenCodeCredentials(api_key="", api_provider="")
