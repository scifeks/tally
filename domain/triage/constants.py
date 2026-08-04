"""Triage audit trail constants."""

from __future__ import annotations

TRIAGE_PROVIDERS = frozenset({"anthropic", "opencode", "openai"})

TRIAGE_MODES = frozenset({"mcp_triage", "auto_triage", "manual"})
