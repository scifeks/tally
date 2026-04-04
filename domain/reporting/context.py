"""Pure domain data object carrying all rendered content for a report."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReportContext:
    """Holds every piece of rendered HTML needed to produce a complete report.

    All section fields contain pre-rendered HTML strings — the template does no
    markdown conversion or data transformation.  Fields with a default of ``""``
    are populated by later pipeline segments (4 and 5); they render as visible
    placeholder blocks until those segments fill them in.
    """

    # ------------------------------------------------------------------ #
    # Report metadata
    # ------------------------------------------------------------------ #
    project_name: str
    company_name: str
    engagement_date: str
    testing_type: str  # "white_box" | "grey_box" | "black_box"
    generated_at: str  # ISO 8601 timestamp

    # ------------------------------------------------------------------ #
    # App-generated structural HTML
    # ------------------------------------------------------------------ #
    toc_html: str

    # ------------------------------------------------------------------ #
    # Blurb sections (pre-written, variable-substituted, markdown-rendered)
    # ------------------------------------------------------------------ #
    confidentiality_html: str
    severity_definitions_html: str
    glossary_html: str

    # ------------------------------------------------------------------ #
    # LLM-drafted sections (markdown-rendered)
    # ------------------------------------------------------------------ #
    executive_summary_html: str
    risk_level_html: str
    critical_issues_html: str
    improvement_points_html: str
    scope_methodology_html: str
    general_recommendations_html: str

    # ------------------------------------------------------------------ #
    # Segment 4 placeholders — empty until Segment 4 fills them
    # ------------------------------------------------------------------ #
    attack_surface_html: str = field(default="")
    vuln_distribution_chart_html: str = field(default="")

    # ------------------------------------------------------------------ #
    # Segment 5 placeholders — empty until Segment 5 fills them
    # ------------------------------------------------------------------ #
    findings_table_html: str = field(default="")
    secrets_exposure_html: str = field(default="")
    detailed_findings_html: str = field(default="")
    false_positive_log_html: str = field(default="")
    raw_sast_html: str = field(default="")
    raw_dast_html: str = field(default="")
    sca_results_html: str = field(default="")
