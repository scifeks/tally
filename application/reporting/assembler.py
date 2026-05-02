"""Report assembler: builds a ReportContext and renders it to PDF."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from application.reporting.attack_surface import AttackSurfaceBuilder
from application.reporting.charts import get_chart_renderer
from application.reporting.draft_query import DraftQueryService
from application.reporting.findings_builder import FindingsBuilder
from application.reporting.resolver import DraftResolver
from application.reporting.tal_id import assign_tal_ids, resolve_prefix
from core.config.manager import ConfigManager
from domain.findings.severity import Severity
from domain.reporting.context import ReportContext
from infrastructure.store import make_store

if TYPE_CHECKING:
    from application.ports.html_template_renderer import HtmlTemplateRenderer
    from application.ports.pdf_renderer import PdfRenderer
    from application.ports.user_prompt import UserPromptPort

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"
_SEVERITY_RANKS = {s.label: s.rank for s in Severity.all_ordered()}

# Human-readable labels for the confidentiality blurb's {{engagement_type}}.
_TESTING_TYPE_LABELS: dict[str, str] = {
    "white_box": "White Box",
    "grey_box": "Grey Box",
    "black_box": "Black Box",
}

# Ordered TOC entries: (display title, section id).
_TOC_ENTRIES: list[tuple[str, str]] = [
    ("Executive Summary", "#exec-summary"),
    ("Scope &amp; Methodology", "#scope-methodology"),
    ("Attack Surface Overview", "#attack-surface"),
    ("Findings", "#findings"),
    ("General Recommendations", "#recommendations"),
    ("Appendix", "#appendix"),
]

# LLM-drafted sections in assembly order.
_DRAFT_SECTIONS: list[tuple[str, str]] = [
    ("executive-summary", "executive_summary_html"),
    ("risk-level", "risk_level_html"),
    ("critical-issues", "critical_issues_html"),
    ("improvement-points", "improvement_points_html"),
    ("scope-and-methodology", "scope_methodology_html"),
    ("general-recommendations", "general_recommendations_html"),
]


def _generate_toc() -> str:
    """Return a static TOC ``<nav>`` fragment.

    Page numbers are populated at PDF render time by WeasyPrint via the
    ``target-counter(attr(href, url), page)`` CSS rule applied to
    ``.toc-pagenum::after``.
    """
    items: list[str] = []
    for title, anchor in _TOC_ENTRIES:
        items.append(
            f"<li>"
            f'<a href="{anchor}">{title}</a>'
            f'<span class="toc-dots"></span>'
            f'<span class="toc-pagenum"></span>'
            f"</li>"
        )
    return '<nav id="toc-nav"><ol>' + "".join(items) + "</ol></nav>"


class ReportAssembler:
    """Orchestrates the full report build: resolve sections, render template, emit PDF.

    Args:
        project:         Active project name.
        base_path:       Application root (the directory containing ``projects/``).
        testing_type:    One of ``"white_box"``, ``"grey_box"``, ``"black_box"``.
        engagement_date: ISO date string (``YYYY-MM-DD``).  If *None*, falls back
                         to the project creation date from ``ProjectConfig``.
    """

    def __init__(
        self,
        project: str,
        base_path: str | Path,
        prompt: UserPromptPort,
        template_renderer: HtmlTemplateRenderer,
        pdf_renderer: PdfRenderer,
        testing_type: str = "white_box",
        engagement_date: str | None = None,
        company_name_override: str | None = None,
        skip_triage: bool = False,
    ) -> None:
        self._project = project
        self._base_path = Path(base_path)
        self._prompt = prompt
        self._template_renderer = template_renderer
        self._pdf_renderer = pdf_renderer
        self._testing_type = testing_type
        self._engagement_date = engagement_date
        self._company_name_override = company_name_override
        self._skip_triage = skip_triage

    # Public API

    def build_context(self) -> ReportContext:
        """Resolve all sections, render blurbs, generate TOC.

        Calls :meth:`DraftResolver.resolve` for each of the six LLM-drafted
        sections and :meth:`DraftResolver.resolve_blurb` for the three static
        blurb sections.  If any resolution fails (missing file or user
        declines), :exc:`SectionMissingError` propagates to the caller.

        Returns:
            Fully populated :class:`ReportContext` with all Segment 4 and
            Segment 5 fields filled in.

        Raises:
            SectionMissingError: A required section cannot be resolved.
            ValueError: The project does not exist.
        """
        manager = ConfigManager(str(self._base_path))
        config = manager.load_project_config(self._project)
        if config is None:
            raise ValueError(f"Project {self._project!r} not found.")

        project_name = config.project_name
        date_str = self._engagement_date or config.created[:10]
        engagement_type = _TESTING_TYPE_LABELS.get(
            self._testing_type, self._testing_type
        )
        override = (self._company_name_override or "").strip()
        company_name = override or config.company_name or "[Company Name]"
        prefix = resolve_prefix(
            config.abbreviation, manager.global_config.report_finding_prefix
        )

        resolver = DraftResolver(self._project, self._base_path, self._prompt)

        # -- LLM-drafted sections ----------------------------------------
        draft_html: dict[str, str] = {}
        for section_name, field_name in _DRAFT_SECTIONS:
            logger.debug("Resolving section %r", section_name)
            draft_html[field_name] = resolver.resolve(section_name)

        # -- Blurbs --------------------------------------------------------
        confidentiality_html = resolver.resolve_blurb(
            "confidentiality",
            {
                "company_name": company_name,
                "engagement_type": engagement_type,
                "engagement_date": date_str,
            },
        )
        severity_definitions_html = resolver.resolve_blurb("severity-definitions")
        glossary_html = resolver.resolve_blurb("glossary")

        # -- Table of contents --------------------------------------------
        toc_html = _generate_toc()

        # -- Segment 4: vulnerability distribution chart ------------------
        _, finding_repo, _, _ = make_store(self._base_path, self._project)
        query_svc = DraftQueryService(finding_repo)
        filtered = query_svc.get_findings_for_report(skip_triage=self._skip_triage)
        sev_counts = query_svc.severity_distribution(filtered)
        chart_html = get_chart_renderer("css").severity_distribution(sev_counts)
        vuln_distribution_chart_html = chart_html

        # -- Segment 4: attack surface overview ---------------------------
        attack_surface_html = AttackSurfaceBuilder(finding_repo).build(filtered)

        # -- Segment 5: Finding ID assignment ---------------------------------
        code_sorted = sorted(
            filtered,
            key=lambda f: (
                _SEVERITY_RANKS.get((f.severity or "").lower(), 99),
                (f.meta.get("title") or f.rule_id or "").lower(),
            ),
        )
        code_with_ids = assign_tal_ids([asdict(f) for f in code_sorted], prefix=prefix)
        finding_repo.reset_tal_ids()
        finding_repo.bulk_update_tal_ids(
            [(f["tal_id"], f["id"]) for f in code_with_ids]
        )
        logger.info("Assigned %d finding IDs to code findings.", len(code_with_ids))

        # -- Segment 5: HTML sections -------------------------------------
        secrets = [f for f in code_with_ids if f.get("segment") == "secrets"]
        builder = FindingsBuilder(prefix=prefix)
        findings_table_html = builder.build_master_table(code_with_ids)
        secrets_exposure_html = builder.build_secrets_cards(secrets)
        detailed_findings_html = builder.build_code_cards(code_with_ids)
        raw_sast_html = builder.build_comprehensive_code_table(code_with_ids)

        return ReportContext(
            project_name=project_name,
            company_name=company_name,
            engagement_date=date_str,
            testing_type=self._testing_type,
            generated_at=datetime.now(UTC).isoformat(),
            toc_html=toc_html,
            confidentiality_html=confidentiality_html,
            severity_definitions_html=severity_definitions_html,
            glossary_html=glossary_html,
            vuln_distribution_chart_html=vuln_distribution_chart_html,
            attack_surface_html=attack_surface_html,
            findings_table_html=findings_table_html,
            secrets_exposure_html=secrets_exposure_html,
            detailed_findings_html=detailed_findings_html,
            raw_sast_html=raw_sast_html,
            **draft_html,
        )

    def render_pdf(self, context: ReportContext) -> bytes:
        """Render *context* to PDF bytes via the injected renderers.

        Steps:
        1. Load ``static/report.css`` from disk.
        2. Render the master template with *context*.
        3. Pass the HTML and CSS to the PdfRenderer.

        Args:
            context: Fully (or partially) populated :class:`ReportContext`.

        Returns:
            Raw PDF bytes.

        Raises:
            PdfRenderError: The PDF backend failed to produce a PDF.
            FileNotFoundError: The CSS stylesheet is missing.
        """
        css = (_STATIC_DIR / "report.css").read_text(encoding="utf-8")
        html = self._template_renderer.render("report.html.j2", {"ctx": context})
        return self._pdf_renderer.render(html, css)

    def build_and_render(self) -> bytes:
        """Convenience: :meth:`build_context` then :meth:`render_pdf`.

        Returns:
            Raw PDF bytes.
        """
        context = self.build_context()
        return self.render_pdf(context)


__all__ = ["ReportAssembler"]
