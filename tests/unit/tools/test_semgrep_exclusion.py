"""Tests for semgrep exclusion pattern generation."""

from unittest.mock import MagicMock

from infrastructure.tools.wrappers.base.semgrep import (
    BaseSemgrepTool,
)


class TestSemgrepExclusionVariants:
    def test_generates_case_variants_for_exclude(self) -> None:
        tool = BaseSemgrepTool.__new__(BaseSemgrepTool)
        context = MagicMock()
        context.repo.name = "test-repo"
        context.repo.path = "/tmp/repo"
        context.service = MagicMock()
        context.excluded_dirs = ["tests", "vendor"]
        context.registry.get_service_path.return_value = "/tmp/repo"

        passes = tool.build_execution_passes(context)
        kwargs = passes[0].kwargs

        exclude = kwargs.get("exclude")
        assert exclude is not None
        assert "tests" in exclude
        assert "Tests" in exclude
        assert "vendor" in exclude
        assert "Vendor" in exclude

    def test_no_exclude_kwarg_when_dirs_empty(self) -> None:
        tool = BaseSemgrepTool.__new__(BaseSemgrepTool)
        context = MagicMock()
        context.repo.name = "test-repo"
        context.repo.path = "/tmp/repo"
        context.service = MagicMock()
        context.excluded_dirs = []
        context.registry.get_service_path.return_value = "/tmp/repo"

        passes = tool.build_execution_passes(context)
        kwargs = passes[0].kwargs

        assert "exclude" not in kwargs
