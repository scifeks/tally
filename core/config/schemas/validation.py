"""Shared validation for tool configuration schemas."""

TOOL_METACHAR_CHARS = frozenset(";&|<>`$")


def has_shell_metacharacters(value: str) -> bool:
    """Return True if value contains shell metacharacters."""
    return any(ch in value for ch in TOOL_METACHAR_CHARS)
