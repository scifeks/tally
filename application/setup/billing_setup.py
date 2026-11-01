"""First-run billing wizard: writes claude.default_billing_method.

Detects which Anthropic credentials are present and offers the user a
choice of default billing method (plan or api), or auto-failover (unset).
Writes the chosen value under ``claude.default_billing_method`` in
``config/global.json`` without touching other config fields.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from application.anthropic.mode_availability import (
    BackgroundModeAvailability,
    BackgroundModeAvailabilityService,
)


class GlobalConfigReadError(ValueError):
    """Raised when config/global.json exists but cannot be parsed as a dict."""


def _summarize_availability(availability: BackgroundModeAvailability) -> str:
    """One-liner summary of what's available."""
    paths: list[str] = []
    if availability.oauth_available:
        paths.append("plan OAuth (claude /login)")
    if availability.api_key_available:
        paths.append("API key (ANTHROPIC_API_KEY)")
    if not paths:
        return "No Anthropic credentials detected."
    return "Available: " + ", ".join(paths) + "."


def _read_global_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise GlobalConfigReadError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise GlobalConfigReadError(
            f"expected a JSON object, got {type(data).__name__}"
        )
    return data


def _write_global_config(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def set_default_billing_method(
    base_path: str,
    value: Literal["plan", "api"] | None,
) -> None:
    """Write claude.default_billing_method to config/global.json.

    Preserves every other field in the file. Writes the key under the
    ``claude`` block, creating that block if absent. ``value=None``
    removes the key (and leaves the rest of the ``claude`` block alone),
    so a user can later clear a prior choice to re-enable auto-failover.
    """
    if value is not None and value not in ("plan", "api"):
        raise ValueError(
            f"default_billing_method must be 'plan' or 'api' or None, got {value!r}"
        )
    cfg_path = Path(base_path) / "config" / "global.json"
    data = _read_global_config(cfg_path)
    claude_block = data.setdefault("claude", {})
    if not isinstance(claude_block, dict):
        raise GlobalConfigReadError(
            f"expected claude block to be a dict, got {type(claude_block).__name__}"
        )
    if value is None:
        claude_block.pop("default_billing_method", None)
    else:
        claude_block["default_billing_method"] = value
    _write_global_config(cfg_path, data)


def run_billing_setup(
    base_path: str,
    availability_service: BackgroundModeAvailabilityService,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    """Interactive first-run step: detect credentials, offer a default.

    Choices are plan, api, auto-failover, or skip. Skip leaves the config
    unchanged.

    ``input_fn`` and ``output_fn`` are injected so tests can drive the
    prompt without touching stdin/stdout.
    """
    cfg_path = Path(base_path) / "config" / "global.json"
    try:
        _read_global_config(cfg_path)
    except GlobalConfigReadError as exc:
        output_fn(f"Cannot read {cfg_path}: {exc}. Fix it manually and re-run.")
        return

    availability = availability_service.evaluate()

    output_fn("")
    output_fn("Tally - Background billing setup")
    output_fn("=" * 40)
    output_fn(
        "Background triage and scan can bill against either your Claude plan "
        "(OAuth) or an API key. See docs/credential-and-billing-model.md for "
        "the four supported configurations."
    )
    output_fn(_summarize_availability(availability))
    output_fn("")
    output_fn("Pick a default for background runs when no --billing-method is set:")
    output_fn("  [1] plan        Always start on plan OAuth, abort on rate limit")
    output_fn("  [2] api         Always start on API key, abort on rate limit")
    output_fn("  [3] auto        Start on plan, auto-fail-over to api on rate limit")
    output_fn("                  (requires both plan and api credentials)")
    output_fn("  [s] skip        Leave the setting unchanged for now")
    output_fn("")

    while True:
        try:
            choice = input_fn("Default billing method [1/2/3/s]: ").strip().lower()
        except EOFError:
            output_fn("No input available, skipping.")
            return
        if choice in ("s", "skip", ""):
            output_fn("Skipped. No change written.")
            return
        try:
            if choice in ("1", "plan"):
                set_default_billing_method(base_path, "plan")
                output_fn("Set claude.default_billing_method = 'plan'.")
                return
            if choice in ("2", "api"):
                set_default_billing_method(base_path, "api")
                output_fn("Set claude.default_billing_method = 'api'.")
                return
            if choice in ("3", "auto"):
                both = availability.oauth_available and availability.api_key_available
                if not both:
                    sources = []
                    if availability.oauth_available:
                        sources.append("plan")
                    if availability.api_key_available:
                        sources.append("api")
                    if sources:
                        detected = f"only {sources[0]}"
                    else:
                        detected = "no credentials"
                    output_fn(
                        "Note: auto-failover requires both plan and api "
                        f"credentials; detected {detected}. "
                        "Setting default to unset anyway."
                    )
                set_default_billing_method(base_path, None)
                output_fn(
                    "Cleared claude.default_billing_method; auto-failover is enabled."
                )
                return
        except GlobalConfigReadError as exc:
            output_fn(f"Cannot read {cfg_path}: {exc}. Fix it manually and re-run.")
            return
        output_fn(f"Unrecognized choice {choice!r}; try 1, 2, 3, or s.")
