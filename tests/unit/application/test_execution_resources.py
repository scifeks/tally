"""Unit tests for ExecutionResources dataclass."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.tools.scan_types.resources import ExecutionResources


def _make_resources(**overrides) -> ExecutionResources:
    defaults: dict = dict(
        executor=MagicMock(),
        registry=MagicMock(),
        factory=MagicMock(),
        event_bus=MagicMock(),
        display=MagicMock(),
    )
    defaults.update(overrides)
    return ExecutionResources(**defaults)


class TestExecutionResources:
    def test_executor_attribute(self) -> None:
        mock_exec = MagicMock()
        res = _make_resources(executor=mock_exec)
        assert res.executor is mock_exec

    def test_registry_attribute(self) -> None:
        mock_reg = MagicMock()
        res = _make_resources(registry=mock_reg)
        assert res.registry is mock_reg

    def test_factory_attribute(self) -> None:
        mock_fac = MagicMock()
        res = _make_resources(factory=mock_fac)
        assert res.factory is mock_fac

    def test_event_bus_attribute(self) -> None:
        mock_eb = MagicMock()
        res = _make_resources(event_bus=mock_eb)
        assert res.event_bus is mock_eb

    def test_display_attribute(self) -> None:
        mock_disp = MagicMock()
        res = _make_resources(display=mock_disp)
        assert res.display is mock_disp

    def test_equality(self) -> None:
        ex, reg, fac, eb, disp = (
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
            MagicMock(),
        )
        sink = MagicMock()
        assert ExecutionResources(ex, reg, fac, eb, disp, sink) == ExecutionResources(
            ex, reg, fac, eb, disp, sink
        )

    def test_event_sink_default_is_null_sink(self) -> None:
        from application.ports.scan_event_sink import NullScanEventSink

        res = _make_resources()
        assert isinstance(res.event_sink, NullScanEventSink)

    def test_event_sink_attribute(self) -> None:
        mock_sink = MagicMock()
        res = _make_resources(event_sink=mock_sink)
        assert res.event_sink is mock_sink
