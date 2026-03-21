"""Unit tests for ExecutionResources dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.tools.scan_types.resources import ExecutionResources


class TestExecutionResources:
    def test_executor_attribute(self) -> None:
        mock_exec = MagicMock()
        res = ExecutionResources(
            executor=mock_exec, registry=MagicMock(), factory=MagicMock()
        )
        assert res.executor is mock_exec

    def test_registry_attribute(self) -> None:
        mock_reg = MagicMock()
        res = ExecutionResources(
            executor=MagicMock(), registry=mock_reg, factory=MagicMock()
        )
        assert res.registry is mock_reg

    def test_factory_attribute(self) -> None:
        mock_fac = MagicMock()
        res = ExecutionResources(
            executor=MagicMock(), registry=MagicMock(), factory=mock_fac
        )
        assert res.factory is mock_fac

    def test_equality(self) -> None:
        ex, reg, fac = MagicMock(), MagicMock(), MagicMock()
        assert ExecutionResources(ex, reg, fac) == ExecutionResources(ex, reg, fac)
