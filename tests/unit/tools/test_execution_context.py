"""Tests for ExecutionContext excluded_dirs population."""

from unittest.mock import MagicMock

from application.tools.scan_types.execution import make_context


class TestMakeContextExcludedDirs:
    def test_populates_excluded_dirs_from_service(self) -> None:
        service = MagicMock()
        service.test_dirs = ["tests"]
        service.ignore_dirs = ["vendor"]

        context = make_context(
            tool_config=MagicMock(),
            project_name="test",
            base_path="/tmp",
            registry=MagicMock(),
            repo=MagicMock(),
            service=service,
            command_config=MagicMock(location="local"),
        )

        assert "tests" in context.excluded_dirs
        assert "vendor" in context.excluded_dirs

    def test_excluded_dirs_empty_when_service_has_none(self) -> None:
        service = MagicMock()
        service.test_dirs = []
        service.ignore_dirs = []

        context = make_context(
            tool_config=MagicMock(),
            project_name="test",
            base_path="/tmp",
            registry=MagicMock(),
            repo=MagicMock(),
            service=service,
            command_config=MagicMock(location="local"),
        )

        assert context.excluded_dirs == []

    def test_excluded_dirs_empty_when_service_is_none(self) -> None:
        context = make_context(
            tool_config=MagicMock(),
            project_name="test",
            base_path="/tmp",
            registry=MagicMock(),
            repo=None,
            service=None,
            command_config=MagicMock(location="local"),
        )

        assert context.excluded_dirs == []
