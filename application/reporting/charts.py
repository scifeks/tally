"""Chart renderer strategy — production backend produces pure HTML/CSS fragments."""

from __future__ import annotations

from abc import ABC, abstractmethod

_SEVERITY_ORDER: tuple[str, ...] = (
    "critical",
    "high",
    "medium",
    "low",
    "informational",
)

_SEVERITY_COLORS: dict[str, str] = {
    "critical": "#c0392b",
    "high": "#e67e22",
    "medium": "#f1c40f",
    "low": "#27ae60",
    "informational": "#7f8c8d",
}

# Minimum bar width (%) so zero-count tiers still render a visible label bar.
_MIN_BAR_PCT = 2


class ChartRenderer(ABC):
    """Strategy interface for chart rendering backends."""

    @abstractmethod
    def severity_distribution(self, counts: dict[str, int]) -> str:
        """Render a severity distribution chart.

        Args:
            counts: Severity name → finding count mapping.  Missing severities
                    are treated as zero.

        Returns:
            Self-contained HTML fragment (no ``<html>`` / ``<body>`` wrapper).
        """


class CSSChartRenderer(ChartRenderer):
    """Chart renderer that produces a pure HTML/CSS fragment with no JavaScript
    and no external dependencies.

    All styles are scoped inside the fragment so it can be embedded into any
    HTML document without polluting the host stylesheet.
    """

    def severity_distribution(self, counts: dict[str, int]) -> str:
        total = sum(counts.get(s, 0) for s in _SEVERITY_ORDER)

        rows: list[str] = []
        for severity in _SEVERITY_ORDER:
            count = counts.get(severity, 0)
            color = _SEVERITY_COLORS[severity]
            if total > 0:
                raw_pct = count / total * 100
                bar_pct = max(_MIN_BAR_PCT, raw_pct)
            else:
                bar_pct = _MIN_BAR_PCT

            rows.append(
                f'<div class="tally-chart-row">'
                f'<span class="tally-chart-label">{severity.capitalize()}</span>'
                f'<div class="tally-chart-track">'
                f'<div class="tally-chart-bar" style="width:{bar_pct:.1f}%;'
                f'background:{color};"></div>'
                f"</div>"
                f'<span class="tally-chart-count">{count}</span>'
                f"</div>"
            )

        rows_html = "\n".join(rows)
        return (
            "<style>"
            ".tally-chart{font-family:Arial,sans-serif;max-width:600px;}"
            ".tally-chart-row{display:flex;align-items:center;"
            "margin-bottom:8px;gap:8px;}"
            ".tally-chart-label{width:110px;font-size:.9em;"
            "text-transform:capitalize;color:#374151;}"
            ".tally-chart-track{flex:1;background:#e5e7eb;"
            "border-radius:4px;height:20px;overflow:hidden;}"
            ".tally-chart-bar{height:100%;border-radius:4px;"
            "transition:width .3s;}"
            ".tally-chart-count{width:36px;text-align:right;"
            "font-size:.9em;color:#374151;font-weight:bold;}"
            "</style>"
            f'<div class="tally-chart">\n{rows_html}\n</div>'
        )


def get_chart_renderer(name: str) -> ChartRenderer:
    """Return the chart renderer for the given backend name.

    Args:
        name: Backend identifier.  Currently ``"css"`` is the only supported
              value.

    Returns:
        Configured :class:`ChartRenderer` instance.

    Raises:
        ValueError: *name* is not a recognised backend.
    """
    if name == "css":
        return CSSChartRenderer()
    raise ValueError(f"Unknown chart backend: {name!r}. Supported: 'css'")
