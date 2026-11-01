"""Build child-process envs for the Claude Agent SDK / claude subprocess.

The Agent SDK and the claude binary both prefer ANTHROPIC_API_KEY over any
OAuth session when both are present. For `plan` billing we must remove the
env var from the child; for `api` billing we must set it, overriding any
ambient value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal


def build_child_env(
    billing_method: Literal["plan", "api"],
    api_key_source: str | None,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    if billing_method == "plan":
        env.pop("ANTHROPIC_API_KEY", None)
        return env
    if billing_method == "api":
        if not api_key_source:
            raise ValueError(
                "billing_method='api' requires a non-empty api_key_source."
            )
        env["ANTHROPIC_API_KEY"] = api_key_source
        return env
    raise ValueError(
        f"Unknown billing_method {billing_method!r}; expected 'plan' or 'api'."
    )
