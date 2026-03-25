"""LLM-based draft generators for each report section."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.llm.base import LLMProvider

from application.reporting.risk_level import RiskLevel

logger = logging.getLogger(__name__)

# Maps section name → generator class; populated by @_register.
SECTION_REGISTRY: dict[str, type[SectionDraftGenerator]] = {}

_SEVERITY_DISPLAY = (
    "critical",
    "high",
    "medium",
    "low",
    "informational",
)
_CONFIDENCE_DISPLAY = ("confirmed", "probable", "potential")


def _register(
    cls: type[SectionDraftGenerator],
) -> type[SectionDraftGenerator]:
    SECTION_REGISTRY[cls.section_name] = cls
    return cls


def _fmt_sev(dist: dict[str, int]) -> str:
    parts = [
        f"{s.capitalize()}: {dist.get(s, 0)}"
        for s in _SEVERITY_DISPLAY
        if dist.get(s, 0) > 0
    ]
    return ", ".join(parts) if parts else "None"


def _fmt_conf(dist: dict[str, int]) -> str:
    parts = [
        f"{c.capitalize()}: {dist.get(c, 0)}"
        for c in _CONFIDENCE_DISPLAY
        if dist.get(c, 0) > 0
    ]
    return ", ".join(parts) if parts else "None"


def _fmt_list(items: list[str], max_enumerate: int) -> str:
    if not items:
        return "(none)"
    if len(items) <= max_enumerate:
        return ", ".join(items)
    return f"{len(items)} items"


def _fmt_repos(repos: list[str], max_enumerate: int) -> str:
    if not repos:
        return "(none recorded)"
    if len(repos) <= max_enumerate:
        return ", ".join(repos)
    return f"{len(repos)} repositories"


class SectionDraftGenerator(ABC):
    """Base class for all report section draft generators."""

    section_name: str

    def __init__(self, llm: LLMProvider, draft_dir: Path) -> None:
        self._llm = llm
        self._draft_dir = draft_dir

    @property
    def draft_path(self) -> Path:
        return self._draft_dir / f"{self.section_name}.md"

    @abstractmethod
    def generate(self, context: dict[str, Any]) -> str:
        """Build prompt, call LLM, return generated content."""

    def _call_llm(self, prompt: str) -> str:
        return self._llm.complete(prompt)


@_register
class ExecutiveSummaryGenerator(SectionDraftGenerator):
    """Generates executive-summary.md."""

    section_name = "executive-summary"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        max_enum: int = ctx.get("max_enumerate", 20)
        repos = _fmt_repos(ctx.get("repos", []), max_enum)
        risk_level: RiskLevel = ctx["risk_level"]
        rc = ctx["risk_counts"]
        sev_dist = ctx["sev_dist"]
        conf_dist = ctx["conf_dist"]

        basis_parts: list[str] = []
        if rc.confirmed_critical:
            basis_parts.append(f"{rc.confirmed_critical} confirmed critical finding(s)")
        if rc.confirmed_high:
            basis_parts.append(f"{rc.confirmed_high} confirmed high finding(s)")
        if rc.prob_confirmed_medium:
            basis_parts.append(
                f"{rc.prob_confirmed_medium} probable/confirmed medium finding(s)"
            )
        risk_basis = "; ".join(basis_parts) if basis_parts else "low-severity findings"

        return (
            "You are writing the executive summary section of a professional"
            " security assessment report.\n\n"
            f"Project: {ctx['project_name']}\n"
            f"Engagement date: {ctx['engagement_date']}\n"
            "Testing type: White box\n"
            f"Repositories scanned: {repos}\n"
            f"Total triaged findings: {ctx['total']}\n"
            f"Severity distribution: {_fmt_sev(sev_dist)}\n"
            f"Confidence distribution: {_fmt_conf(conf_dist)}\n"
            f"Overall risk level: {risk_level.value}\n"
            f"Risk level basis: {risk_basis}\n\n"
            "Write a 2-3 paragraph executive summary in plain English for a"
            " non-technical audience (CEO, project manager, board level).\n\n"
            "Requirements:\n"
            "- Convey the overall risk level, what was tested, and the most"
            " significant areas of concern.\n"
            "- Do not reference tool names, rule IDs, or technical jargon.\n"
            "- Do not speculate beyond the data provided.\n"
            "- Begin directly with the first sentence of the summary.\n\n"
            "Write only the executive summary text."
        )


@_register
class RiskLevelSectionGenerator(SectionDraftGenerator):
    """Generates risk-level.md."""

    section_name = "risk-level"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        risk_level: RiskLevel = ctx["risk_level"]
        rc = ctx["risk_counts"]
        sev_dist = ctx["sev_dist"]
        conf_dist = ctx["conf_dist"]

        return (
            "You are writing the risk level section of a professional"
            " security assessment report.\n\n"
            f"Overall risk level: {risk_level.value}\n"
            f"Severity distribution: {_fmt_sev(sev_dist)}\n"
            f"Confidence distribution: {_fmt_conf(conf_dist)}\n"
            f"Confirmed critical findings: {rc.confirmed_critical}\n"
            f"Confirmed high findings: {rc.confirmed_high}\n"
            "Probable or confirmed medium findings:"
            f" {rc.prob_confirmed_medium}\n"
            f"Recurring findings (seen in multiple scans): {rc.recurring}\n\n"
            f"Write a single focused paragraph explaining the"
            f" {risk_level.value} overall risk level in business terms.\n\n"
            "Requirements:\n"
            f"- Explain what contributed to the {risk_level.value} rating"
            " and what it means for the organisation.\n"
            "- Interpret the numbers in business context — do not simply"
            " restate raw counts.\n"
            "- Do not speculate beyond the data provided.\n\n"
            "Write only the paragraph text."
        )


@_register
class CriticalIssuesGenerator(SectionDraftGenerator):
    """Generates critical-issues.md."""

    section_name = "critical-issues"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        findings: list[dict[str, Any]] = ctx["top_findings"]

        entries: list[str] = []
        for f in findings:
            tal_id = f.get("tal_id") or "(no finding ID)"
            severity = (f.get("severity") or "").capitalize()
            confidence = (f.get("confidence") or "").capitalize()
            description = f.get("description") or "(no description)"
            business_impact = f.get("business_impact") or ""
            tool = f.get("tool") or ""

            lines = [
                f"Finding ID: {tal_id}",
                f"Severity: {severity} | Confidence: {confidence}",
            ]
            if tool:
                lines.append(f"Tool: {tool}")
            lines.append(f"Description: {description}")
            if business_impact:
                lines.append(f"Business impact: {business_impact}")
            entries.append("\n".join(lines))

        findings_block = "\n\n".join(entries)

        prefix = ctx.get("finding_id_prefix", "")
        example_id = f"{prefix}-001" if prefix else "001"
        return (
            "You are writing the critical issues section of a professional"
            " security assessment report.\n\n"
            "The following are the top findings from this engagement, ordered"
            " by severity then confidence:\n\n"
            f"{findings_block}\n\n"
            "Write a brief narrative describing each finding. For each:\n"
            f"- Begin with a reference to its finding ID (e.g. {example_id}).\n"
            "- Describe what the issue is and why it matters to the business"
            " in 1-2 sentences.\n"
            "- Do not include technical detail, remediation steps, or"
            " tool-specific information.\n"
            "- Do not speculate beyond the information provided.\n\n"
            "Write only the narrative text, with one entry per finding."
        )


@_register
class ImprovementPointsGenerator(SectionDraftGenerator):
    """Generates improvement-points.md."""

    section_name = "improvement-points"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        groups: list[tuple[str, int]] = ctx["risk_type_groups"]
        sev_dist = ctx["sev_dist"]

        if groups:
            groups_block = "\n".join(
                f"- {rt} ({count} occurrence{'s' if count != 1 else ''})"
                for rt, count in groups
            )
        else:
            groups_block = "(no risk type data available)"

        return (
            "You are writing the improvement points section of a professional"
            " security assessment report.\n\n"
            "The most frequently occurring vulnerability categories across"
            " all findings are:\n\n"
            f"{groups_block}\n\n"
            f"Severity distribution for context: {_fmt_sev(sev_dist)}\n\n"
            "Write 3-6 improvement themes describing recurring patterns"
            " observed across the engagement.\n\n"
            "Requirements:\n"
            "- Each theme must describe a category of issues, not individual"
            " findings.\n"
            "- Each theme must be 2-3 sentences.\n"
            "- Themes must be specific to the patterns listed above, not"
            " generic security advice.\n"
            "- Do not reference specific tool names, rule IDs, or finding IDs.\n\n"
            "Format: a brief heading for each theme followed by 2-3 sentences"
            " of description.\n\n"
            "Write only the improvement themes."
        )


@_register
class ScopeMethodologyGenerator(SectionDraftGenerator):
    """Generates scope-and-methodology.md."""

    section_name = "scope-and-methodology"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        max_enum: int = ctx.get("max_enumerate", 20)
        repos = _fmt_repos(ctx.get("repos", []), max_enum)
        tools = _fmt_list(ctx.get("tools", []), max_enum)
        url_hosts: list[str] = ctx.get("url_hosts", [])
        hosts: list[str] = ctx.get("hosts", [])
        ecosystems: list[str] = ctx.get("ecosystems", [])
        tools_blurb: str = ctx.get("tools_blurb", "")

        network_lines: list[str] = []
        if hosts:
            network_lines.append(
                f"Network hosts in scope: {_fmt_list(hosts, max_enum)}"
            )
        if url_hosts:
            network_lines.append(
                f"Web endpoints in scope: {_fmt_list(url_hosts, max_enum)}"
            )
        network_section = ("\n".join(network_lines) + "\n") if network_lines else ""

        ecosystem_section = ""
        if ecosystems:
            ecosystem_section = (
                f"Software ecosystems scanned: {_fmt_list(ecosystems, max_enum)}\n"
            )

        return (
            "You are writing the scope and methodology section of a"
            " professional security assessment report.\n\n"
            f"Project: {ctx['project_name']}\n"
            f"Engagement date: {ctx['engagement_date']}\n"
            "Testing type: White box\n"
            f"Repositories scanned: {repos}\n"
            f"Tools used: {tools}\n"
            f"{network_section}"
            f"{ecosystem_section}\n"
            "The following pre-written blurb describes the tools used."
            " Embed it naturally in this section — do not reproduce it"
            " verbatim as a separate block:\n\n"
            "---\n"
            f"{tools_blurb}\n"
            "---\n\n"
            "Write a professional scope and methodology section covering:\n"
            "- What was tested (repositories, endpoints, or ecosystems in"
            " scope).\n"
            "- The testing tools and what security domains they covered.\n"
            "- The testing approach (white box — full source code access"
            " provided).\n"
            "- Any relevant limitations.\n\n"
            "The tools-used blurb must appear as a natural part of the"
            " section, not as a separate quoted block. Do not repeat"
            " information verbatim.\n\n"
            "Write only the section text."
        )


@_register
class GeneralRecommendationsGenerator(SectionDraftGenerator):
    """Generates general-recommendations.md."""

    section_name = "general-recommendations"

    def generate(self, context: dict[str, Any]) -> str:
        return self._call_llm(self._build_prompt(context))

    def _build_prompt(self, ctx: dict[str, Any]) -> str:
        groups: list[tuple[str, int]] = ctx["risk_type_groups"]
        recurring_by_rt: dict[str, list[dict[str, Any]]] = ctx["recurring_by_risk_type"]
        sev_dist = ctx["sev_dist"]
        improvement_draft: str | None = ctx.get("improvement_points_draft")

        if groups:
            groups_block = "\n".join(
                f"- {rt} ({count} occurrence{'s' if count != 1 else ''})"
                for rt, count in groups
            )
        else:
            groups_block = "(no risk type data available)"

        if recurring_by_rt:
            recurring_lines = [
                f"- {rt}: {len(fs)} recurring finding(s)"
                for rt, fs in recurring_by_rt.items()
            ]
            recurring_block = "\n".join(recurring_lines)
        else:
            recurring_block = "(no recurring findings)"

        improvement_context = ""
        if improvement_draft:
            improvement_context = (
                "\nFor coherence, the improvement points section has already"
                " been drafted. Your recommendations should complement it —"
                " improvement points describe what was found; recommendations"
                " describe what to do about it:\n\n"
                f"---\n{improvement_draft}\n---\n"
            )

        return (
            "You are writing the general recommendations section of a"
            " professional security assessment report.\n\n"
            "The most frequently occurring vulnerability categories are:\n\n"
            f"{groups_block}\n\n"
            "Recurring findings grouped by category:\n\n"
            f"{recurring_block}\n\n"
            f"Severity distribution for context: {_fmt_sev(sev_dist)}\n"
            f"{improvement_context}\n"
            "Write a general recommendations section grouped by theme.\n\n"
            "Requirements:\n"
            "- Each recommendation group must be named and specific to"
            " patterns observed in this engagement, not generic advice.\n"
            "- Each group must include a 2-4 sentence description of the"
            " pattern and its implications.\n"
            "- Each group must include a brief, actionable remediation"
            " direction.\n"
            "- Cover only categories with sufficient evidence in the data.\n\n"
            "Format: named recommendation groups, each followed by a"
            " description and remediation direction.\n\n"
            "Write only the recommendations section text."
        )
