"""Unit tests for ToolWrapperFactory (application.tools.factory)."""

from __future__ import annotations

import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.tools.factory import ToolWrapperFactory
from domain.tools.base import ToolResult
from domain.tools.interface import ExecutionContext, ExecutionPass, ToolInterface


class _StubTool(ToolInterface):
    """Minimal concrete ToolInterface implementation for use in tests."""

    def __init__(self, *, config: Any) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return "stub"

    @property
    def scan_segment(self) -> str:
        return "test"

    @property
    def findings_exit_ok(self) -> bool:
        return False

    @property
    def language_gates(self) -> list[str]:
        return []

    @property
    def requires_base_urls(self) -> bool:
        return False

    @property
    def always_run(self) -> bool:
        return False

    @property
    def candidate_commands(self) -> list[str]:
        return []

    @property
    def skip(self) -> bool:
        return False

    def build_execution_passes(self, context: ExecutionContext) -> list[ExecutionPass]:
        return []

    def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
        return MagicMock(spec=ToolResult)

    def count_findings(self, parsed_data: dict[str, Any]) -> int:
        return 0


@pytest.mark.unit
class TestToolWrapperFactory:
    def setup_method(self) -> None:
        self.factory = ToolWrapperFactory()

    def test_create_returns_stub_tool_instance(self) -> None:
        config = MagicMock()
        config.location = "local"
        module_name = "infrastructure.tools.wrappers.local.my_tool"
        fake_module = types.ModuleType(module_name)
        _StubTool.__module__ = module_name
        fake_module._StubTool = _StubTool  # type: ignore[attr-defined]

        with patch(
            "application.tools.factory.importlib.import_module",
            return_value=fake_module,
        ) as mock_import:
            result = self.factory.create("my-tool", config)

        mock_import.assert_called_once_with(module_name)
        assert isinstance(result, _StubTool)
        assert result.config is config

    def test_create_raises_value_error_when_module_is_empty(self) -> None:
        config = MagicMock()
        config.location = "local"
        fake_module = types.ModuleType("infrastructure.tools.wrappers.local.ghost_tool")

        with patch(
            "application.tools.factory.importlib.import_module",
            return_value=fake_module,
        ):
            with pytest.raises(ValueError, match="No ToolInterface implementation"):
                self.factory.create("ghost-tool", config)

    def test_create_raises_value_error_when_only_abstract_subclass_present(
        self,
    ) -> None:
        config = MagicMock()
        config.location = "local"
        module_name = "infrastructure.tools.wrappers.local.abstract_tool"

        # An abstract subclass — deliberately leaves build_execution_passes
        # unimplemented so inspect.isabstract returns True.
        class _AbstractSubTool(ToolInterface):
            __module__ = module_name

            @property
            def name(self) -> str:
                return "abstract"

            @property
            def scan_segment(self) -> str:
                return "test"

            @property
            def findings_exit_ok(self) -> bool:
                return False

            @property
            def language_gates(self) -> list[str]:
                return []

            @property
            def requires_base_urls(self) -> bool:
                return False

            @property
            def always_run(self) -> bool:
                return False

            @property
            def candidate_commands(self) -> list[str]:
                return []

            @property
            def skip(self) -> bool:
                return False

            # build_execution_passes, merge_pass_results, count_findings
            # intentionally not implemented — keeps class abstract.

        fake_module = types.ModuleType(module_name)
        fake_module._AbstractSubTool = _AbstractSubTool  # type: ignore[attr-defined]

        with patch(
            "application.tools.factory.importlib.import_module",
            return_value=fake_module,
        ):
            with pytest.raises(ValueError, match="No ToolInterface implementation"):
                self.factory.create("abstract-tool", config)

    def test_create_raises_value_error_when_class_belongs_to_wrong_module(
        self,
    ) -> None:
        config = MagicMock()
        config.location = "local"
        module_name = "infrastructure.tools.wrappers.local.real_tool"

        # A fresh concrete subclass whose __module__ points elsewhere.
        class _WrongModuleTool(ToolInterface):
            __module__ = "some.other.module"

            def __init__(self, *, config: Any) -> None:
                self.config = config

            @property
            def name(self) -> str:
                return "wrong"

            @property
            def scan_segment(self) -> str:
                return "test"

            @property
            def findings_exit_ok(self) -> bool:
                return False

            @property
            def language_gates(self) -> list[str]:
                return []

            @property
            def requires_base_urls(self) -> bool:
                return False

            @property
            def always_run(self) -> bool:
                return False

            @property
            def candidate_commands(self) -> list[str]:
                return []

            @property
            def skip(self) -> bool:
                return False

            def build_execution_passes(
                self, context: ExecutionContext
            ) -> list[ExecutionPass]:
                return []

            def merge_pass_results(self, pass_results: list[ToolResult]) -> ToolResult:
                return MagicMock(spec=ToolResult)

            def count_findings(self, parsed_data: dict[str, Any]) -> int:
                return 0

        fake_module = types.ModuleType(module_name)
        fake_module._WrongModuleTool = _WrongModuleTool  # type: ignore[attr-defined]

        with patch(
            "application.tools.factory.importlib.import_module",
            return_value=fake_module,
        ):
            with pytest.raises(ValueError, match="No ToolInterface implementation"):
                self.factory.create("real-tool", config)

    def test_create_converts_hyphens_to_underscores_in_module_name(
        self,
    ) -> None:
        config = MagicMock()
        config.location = "local"
        expected_module = "infrastructure.tools.wrappers.local.npm_audit"
        fake_module = types.ModuleType(expected_module)

        with patch(
            "application.tools.factory.importlib.import_module",
            return_value=fake_module,
        ) as mock_import:
            with pytest.raises(ValueError):
                self.factory.create("npm-audit", config)

        mock_import.assert_called_once_with(expected_module)
