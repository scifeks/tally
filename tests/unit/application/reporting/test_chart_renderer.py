"""Unit tests for application.reporting.charts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.charts import (  # noqa: E402
    ChartRenderer,
    CSSChartRenderer,
    get_chart_renderer,
)

_COUNTS = {
    "critical": 3,
    "high": 7,
    "medium": 12,
    "low": 5,
    "informational": 1,
}


class TestGetChartRenderer:
    def test_css_returns_css_chart_renderer(self) -> None:
        renderer = get_chart_renderer("css")
        assert isinstance(renderer, CSSChartRenderer)

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown chart backend"):
            get_chart_renderer("unknown_backend")

    def test_renderer_is_abstract_base(self) -> None:
        assert issubclass(CSSChartRenderer, ChartRenderer)


class TestCSSChartRenderer:
    def _render(self, counts: dict[str, int] | None = None) -> str:
        renderer = CSSChartRenderer()
        return renderer.severity_distribution(counts if counts is not None else _COUNTS)

    def test_all_five_tiers_present(self) -> None:
        output = self._render()
        for tier in ("Critical", "High", "Medium", "Low", "Informational"):
            assert tier in output, f"Missing tier: {tier}"

    def test_output_is_fragment_not_full_document(self) -> None:
        output = self._render()
        assert "<html" not in output
        assert "<body" not in output
        assert "<head" not in output

    def test_zero_count_tier_still_renders(self) -> None:
        counts = {
            "critical": 0,
            "high": 5,
            "medium": 0,
            "low": 2,
            "informational": 0,
        }
        output = self._render(counts)
        assert "Critical" in output
        assert "Medium" in output
        assert "Informational" in output

    def test_zero_count_tier_has_minimum_bar_width(self) -> None:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "informational": 0}
        output = self._render(counts)
        assert "2.0%" in output

    def test_counts_appear_in_output(self) -> None:
        output = self._render()
        assert ">3<" in output or ">3 <" in output or "3</span>" in output

    def test_correct_colors_used(self) -> None:
        output = self._render()
        assert "#c0392b" in output
        assert "#e67e22" in output
        assert "#f1c40f" in output
        assert "#27ae60" in output
        assert "#7f8c8d" in output

    def test_empty_counts_renders_without_error(self) -> None:
        output = self._render({})
        assert "Critical" in output
        assert "Informational" in output

    def test_returns_string(self) -> None:
        assert isinstance(self._render(), str)
