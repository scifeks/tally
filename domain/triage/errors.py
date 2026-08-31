"""Triage mode enforcement errors."""

from __future__ import annotations


class TriageModeError(RuntimeError):
    """Auto-triage rejected: provider requires MCP mode."""
