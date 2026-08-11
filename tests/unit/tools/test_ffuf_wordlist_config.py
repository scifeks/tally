"""Unit tests for ffuf argument profile requirement."""

from infrastructure.tools.wrappers.base.ffuf import BaseFFufTool


class TestFFufRequiresArgProfile:
    """ffuf requires an argument profile for wordlist configuration."""

    def test_requires_arg_profile(self):
        tool = BaseFFufTool()
        assert tool.requires_arg_profile is True

    def test_build_execution_passes_returns_empty(self):
        from unittest.mock import MagicMock

        tool = BaseFFufTool()
        ctx = MagicMock()
        passes = tool.build_execution_passes(ctx)
        assert passes == []
