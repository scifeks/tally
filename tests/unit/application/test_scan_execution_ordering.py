"""Unit tests for ordered_repo_tools — discovery-first ordering (ADR-00014)."""

from __future__ import annotations

from unittest.mock import MagicMock

from application.tools.scan_types.execution import ordered_repo_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool(name: str, segment: str, is_discovery: bool = False) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.scan_segment = segment
    t.is_discovery_tool = is_discovery
    return t


def _make_registry(tools: list[MagicMock]) -> MagicMock:
    registry = MagicMock()
    tool_map = {t.name: t for t in tools}
    registry.get_tool.side_effect = lambda name: tool_map.get(name)
    return registry


# ---------------------------------------------------------------------------
# Ordering tests
# ---------------------------------------------------------------------------


class TestOrderedRepoTools:
    def test_discovery_tools_run_before_scanners(self) -> None:
        tools = [
            _make_tool("dalfox", "web"),
            _make_tool("katana", "web", is_discovery=True),
            _make_tool("noir", "web", is_discovery=True),
            _make_tool("xsstrike", "web"),
            _make_tool("zap", "web"),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools(
            {"dalfox", "katana", "noir", "xsstrike", "zap"}, registry
        )
        assert result == ["katana", "noir", "dalfox", "xsstrike", "zap"]

    def test_discovery_tools_alphabetical_among_themselves(self) -> None:
        tools = [
            _make_tool("noir", "web", is_discovery=True),
            _make_tool("katana", "web", is_discovery=True),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"noir", "katana"}, registry)
        assert result == ["katana", "noir"]

    def test_scanners_alphabetical_among_themselves(self) -> None:
        tools = [
            _make_tool("zap", "web"),
            _make_tool("dalfox", "web"),
            _make_tool("xsstrike", "web"),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"zap", "dalfox", "xsstrike"}, registry)
        assert result == ["dalfox", "xsstrike", "zap"]

    def test_single_discovery_tool_first(self) -> None:
        tools = [
            _make_tool("zap", "web"),
            _make_tool("katana", "web", is_discovery=True),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"zap", "katana"}, registry)
        assert result == ["katana", "zap"]

    def test_no_discovery_tools_alphabetical(self) -> None:
        tools = [
            _make_tool("zap", "web"),
            _make_tool("dalfox", "web"),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"zap", "dalfox"}, registry)
        assert result == ["dalfox", "zap"]

    def test_segment_order_preserved(self) -> None:
        tools = [
            _make_tool("bandit", "sast"),
            _make_tool("katana", "web", is_discovery=True),
            _make_tool("zap", "web"),
        ]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"bandit", "katana", "zap"}, registry)
        sast_idx = result.index("bandit")
        katana_idx = result.index("katana")
        zap_idx = result.index("zap")
        assert sast_idx < katana_idx < zap_idx

    def test_empty_tool_set_returns_empty(self) -> None:
        registry = _make_registry([])
        result = ordered_repo_tools(set(), registry)
        assert result == []

    def test_unknown_tool_excluded(self) -> None:
        tools = [_make_tool("katana", "web", is_discovery=True)]
        registry = _make_registry(tools)
        result = ordered_repo_tools({"katana", "unknown-tool"}, registry)
        assert "unknown-tool" not in result
        assert "katana" in result
