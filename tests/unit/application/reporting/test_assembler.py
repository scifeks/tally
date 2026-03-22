"""Unit tests for application.reporting.assembler."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.assembler import (  # noqa: E402
    _TOC_ENTRIES,
    ReportAssembler,
    _generate_toc,
)
from application.reporting.resolver import SectionMissingError  # noqa: E402
from domain.reporting.context import ReportContext  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_project_config(name: str = "acme") -> Any:
    """Return a minimal object that satisfies ConfigManager.load_project_config()."""

    @dataclass
    class FakeConfig:
        project_name: str = name
        created: str = "2026-03-22T12:00:00"

    return FakeConfig()


def _make_assembler(tmp_path: Path) -> ReportAssembler:
    return ReportAssembler(
        project="acme",
        base_path=tmp_path,
        company_name="ACME Corp",
        testing_type="white_box",
        engagement_date="2026-03-22",
    )


# ---------------------------------------------------------------------------
# TOC generation
# ---------------------------------------------------------------------------


class TestGenerateToc:
    def test_returns_string(self) -> None:
        html = _generate_toc()
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_all_section_anchors(self) -> None:
        html = _generate_toc()
        for _, anchor in _TOC_ENTRIES:
            assert anchor in html, f"Missing TOC anchor {anchor!r}"

    def test_is_nav_element(self) -> None:
        html = _generate_toc()
        assert "<nav" in html

    def test_toc_pagenum_spans_present(self) -> None:
        html = _generate_toc()
        assert "toc-pagenum" in html


# ---------------------------------------------------------------------------
# ReportAssembler.build_context()
# ---------------------------------------------------------------------------


class TestBuildContext:
    def _patch_resolver(self, side_effect_resolve=None, side_effect_blurb=None):
        """Patch DraftResolver so no real files are needed."""
        mock_resolver = MagicMock()
        mock_resolver.resolve.side_effect = side_effect_resolve or (
            lambda section: f"<p>HTML for {section}</p>"
        )
        mock_resolver.resolve_blurb.side_effect = side_effect_blurb or (
            lambda name, variables=None: f"<p>Blurb: {name}</p>"
        )
        return mock_resolver

    def test_resolve_called_for_all_six_sections(self, tmp_path: Path) -> None:
        mock_resolver = self._patch_resolver()
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config()
            )
            assembler = _make_assembler(tmp_path)
            assembler.build_context()

        assert mock_resolver.resolve.call_count == 6

    def test_resolve_blurb_called_for_three_blurbs(self, tmp_path: Path) -> None:
        mock_resolver = self._patch_resolver()
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config()
            )
            assembler = _make_assembler(tmp_path)
            assembler.build_context()

        assert mock_resolver.resolve_blurb.call_count == 3

    def test_context_has_correct_metadata(self, tmp_path: Path) -> None:
        mock_resolver = self._patch_resolver()
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config("acme")
            )
            assembler = _make_assembler(tmp_path)
            ctx = assembler.build_context()

        assert ctx.project_name == "acme"
        assert ctx.company_name == "ACME Corp"
        assert ctx.engagement_date == "2026-03-22"
        assert ctx.testing_type == "white_box"

    def test_segment4_fields_populated_and_segment5_fields_empty(
        self, tmp_path: Path
    ) -> None:
        """Segment 4 fields are populated by build_context; Segment 5 remain empty."""
        mock_resolver = self._patch_resolver()
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config()
            )
            assembler = _make_assembler(tmp_path)
            ctx = assembler.build_context()

        # Segment 4 — populated with HTML (graceful degradation if no data).
        assert ctx.attack_surface_html != ""
        assert ctx.vuln_distribution_chart_html != ""
        # Segment 5 — still empty until Segment 5 is implemented.
        assert ctx.findings_table_html == ""
        assert ctx.false_positive_log_html == ""

    def test_section_missing_error_propagates(self, tmp_path: Path) -> None:
        mock_resolver = self._patch_resolver(
            side_effect_resolve=SectionMissingError("missing!")
        )
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config()
            )
            assembler = _make_assembler(tmp_path)
            with pytest.raises(SectionMissingError):
                assembler.build_context()

    def test_missing_project_raises_value_error(self, tmp_path: Path) -> None:
        with patch("application.reporting.assembler.ConfigManager") as mock_cfg:
            mock_cfg.return_value.load_project_config.return_value = None
            assembler = _make_assembler(tmp_path)
            with pytest.raises(ValueError, match="not found"):
                assembler.build_context()

    def test_engagement_date_fallback_from_config(self, tmp_path: Path) -> None:
        """When engagement_date is not given, created[:10] from config is used."""
        mock_resolver = self._patch_resolver()
        with (
            patch("application.reporting.assembler.ConfigManager") as mock_cfg,
            patch(
                "application.reporting.assembler.DraftResolver",
                return_value=mock_resolver,
            ),
        ):
            mock_cfg.return_value.load_project_config.return_value = (
                _fake_project_config()
            )
            assembler = ReportAssembler(
                project="acme",
                base_path=tmp_path,
                company_name="ACME Corp",
                # engagement_date deliberately omitted
            )
            ctx = assembler.build_context()

        assert ctx.engagement_date == "2026-03-22"


# ---------------------------------------------------------------------------
# ReportAssembler.render_pdf()
# ---------------------------------------------------------------------------


class TestRenderPdf:
    def _make_context(self) -> ReportContext:
        return ReportContext(
            project_name="acme",
            company_name="ACME Corp",
            engagement_date="2026-03-22",
            testing_type="white_box",
            generated_at="2026-03-22T00:00:00+00:00",
            toc_html="<nav><ol></ol></nav>",
            confidentiality_html="<p>Confidential</p>",
            severity_definitions_html="<p>Sev defs</p>",
            glossary_html="<p>Glossary</p>",
            executive_summary_html="<p>Summary</p>",
            risk_level_html="<p>High</p>",
            critical_issues_html="<p>Issues</p>",
            improvement_points_html="<p>Improvements</p>",
            scope_methodology_html="<p>Scope</p>",
            general_recommendations_html="<p>Recommendations</p>",
        )

    def test_render_passes_non_empty_html_to_renderer(self, tmp_path: Path) -> None:
        captured: dict[str, str] = {}

        def fake_render(html: str, css: str) -> bytes:
            captured["html"] = html
            captured["css"] = css
            return b"%PDF-fake"

        fake_renderer = MagicMock()
        fake_renderer.render.side_effect = fake_render

        assembler = _make_assembler(tmp_path)
        ctx = self._make_context()

        with patch(
            "application.reporting.assembler.get_pdf_renderer",
            return_value=fake_renderer,
        ):
            result = assembler.render_pdf(ctx)

        assert result == b"%PDF-fake"
        assert len(captured["html"]) > 100
        assert "<!DOCTYPE html>" in captured["html"]

    def test_render_loads_css_from_static_dir(self, tmp_path: Path) -> None:
        """The CSS string passed to the renderer comes from the static file."""
        captured: dict[str, str] = {}

        def fake_render(html: str, css: str) -> bytes:
            captured["css"] = css
            return b"%PDF"

        fake_renderer = MagicMock()
        fake_renderer.render.side_effect = fake_render

        assembler = _make_assembler(tmp_path)
        ctx = self._make_context()

        with patch(
            "application.reporting.assembler.get_pdf_renderer",
            return_value=fake_renderer,
        ):
            assembler.render_pdf(ctx)

        assert "--color-critical" in captured["css"]
        assert "--color-background" in captured["css"]

    def test_template_renders_all_section_ids(self, tmp_path: Path) -> None:
        """All major section IDs appear in the rendered HTML."""
        captured: dict[str, str] = {}

        def fake_render(html: str, css: str) -> bytes:
            captured["html"] = html
            return b"%PDF"

        fake_renderer = MagicMock()
        fake_renderer.render.side_effect = fake_render

        assembler = _make_assembler(tmp_path)
        ctx = self._make_context()

        with patch(
            "application.reporting.assembler.get_pdf_renderer",
            return_value=fake_renderer,
        ):
            assembler.render_pdf(ctx)

        html = captured["html"]
        for section_id in (
            "exec-summary",
            "scope-methodology",
            "attack-surface",
            "findings",
            "recommendations",
            "appendix",
        ):
            assert f'id="{section_id}"' in html, f"Missing section id={section_id!r}"

    def test_placeholder_shown_when_segment4_fields_empty(self, tmp_path: Path) -> None:
        """Placeholder text visible when attack_surface_html is empty."""
        captured: dict[str, str] = {}

        def fake_render(html: str, css: str) -> bytes:
            captured["html"] = html
            return b"%PDF"

        fake_renderer = MagicMock()
        fake_renderer.render.side_effect = fake_render

        assembler = _make_assembler(tmp_path)
        ctx = self._make_context()  # attack_surface_html defaults to ""

        with patch(
            "application.reporting.assembler.get_pdf_renderer",
            return_value=fake_renderer,
        ):
            assembler.render_pdf(ctx)

        assert "placeholder" in captured["html"]
        assert "Segment 4" in captured["html"]

    def test_content_injected_when_segment4_fields_populated(
        self, tmp_path: Path
    ) -> None:
        """Placeholder absent when attack_surface_html is provided."""
        captured: dict[str, str] = {}

        def fake_render(html: str, css: str) -> bytes:
            captured["html"] = html
            return b"%PDF"

        fake_renderer = MagicMock()
        fake_renderer.render.side_effect = fake_render

        assembler = _make_assembler(tmp_path)
        ctx = self._make_context()
        ctx.attack_surface_html = "<p>Real attack surface data</p>"

        with patch(
            "application.reporting.assembler.get_pdf_renderer",
            return_value=fake_renderer,
        ):
            assembler.render_pdf(ctx)

        assert "Real attack surface data" in captured["html"]
