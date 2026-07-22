"""Report generation from aggregated RAG findings."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from domain.findings.severity import Severity

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort

logger = logging.getLogger(__name__)

_SCA_TOOLS = ("osv-scanner", "pip-audit", "npm-audit", "composer-audit")


class ReportGenerator:
    """Generate security reports from findings stored in the RAG engine."""

    def __init__(
        self,
        rag_engine: object,
        project: str,
        finding_repo: FindingRepositoryPort,
        skip_triage: bool = False,
    ) -> None:
        self._engine = rag_engine
        self.project = project
        self._finding_repo = finding_repo
        self._skip_triage = skip_triage

    def generate(
        self,
        output_format: str = "markdown",
        output_path: str | None = None,
    ) -> str:
        """Aggregate findings and render a report in the requested format.

        Supported formats: 'markdown', 'html', 'json'.
        """
        aggregated = self._aggregate_findings()

        if output_format == "markdown":
            content = self._render_markdown(aggregated)
        elif output_format == "html":
            content = self._render_html(aggregated)
        elif output_format == "json":
            content = self._render_json(aggregated)
        else:
            raise ValueError(
                f"Unknown format: {output_format!r}. Use markdown, html, or json."
            )

        if output_path:
            dest = Path(output_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")

        return content

    def _aggregate_findings(self) -> dict[str, Any]:
        """Pull all findings from RAG grouped by tool."""
        generated_at = datetime.now(UTC).isoformat()
        findings_by_tool: dict[str, list[dict[str, Any]]] = {}
        by_severity = {s.label: 0 for s in Severity.all_ordered()}

        try:
            if self._skip_triage:
                findings_list = (
                    self._finding_repo.get_findings_marked_for_report_deserialized()
                )
            else:
                findings_list = (
                    self._finding_repo.get_reportable_findings_deserialized()
                )
            for finding in findings_list:
                tool = finding.get("tool", "unknown")
                findings_by_tool.setdefault(tool, []).append(finding)
                severity = (finding.get("severity") or "").lower()
                if severity in by_severity:
                    by_severity[severity] += 1
        except Exception as exc:
            logger.warning("Failed to fetch findings for report: %s", exc)

        total = sum(len(v) for v in findings_by_tool.values())
        by_tool = {tool: len(items) for tool, items in findings_by_tool.items()}

        return {
            "project_name": self.project,
            "generated_at": generated_at,
            "summary": {
                "total_findings": total,
                "by_tool": by_tool,
                "by_severity": by_severity,
            },
            "findings": findings_by_tool,
        }

    def _render_markdown(self, aggregated: dict[str, Any]) -> str:
        """Render aggregated findings as a markdown report."""
        project_name = aggregated["project_name"]
        generated_at = aggregated["generated_at"]
        summary = aggregated["summary"]
        findings = aggregated["findings"]
        by_sev = summary["by_severity"]

        lines = [
            f"# Tally Security Report: {project_name}",
            f"Generated: {generated_at}",
            "",
            "## Executive Summary",
            f"Total findings: {summary['total_findings']}",
            (
                f"Critical: {by_sev.get('critical', 0)} | "
                f"High: {by_sev.get('high', 0)} | "
                f"Medium: {by_sev.get('medium', 0)} | "
                f"Low: {by_sev.get('low', 0)}"
            ),
            "",
            "## Findings by Tool",
        ]

        semgrep_findings = findings.get("semgrep", [])
        if semgrep_findings:
            lines += [
                "",
                "### SAST (semgrep)",
                "| Severity | Rule | File | Line | CWE |",
                "|----------|------|------|------|-----|",
            ]
            for f in semgrep_findings:
                lines.append(
                    f"| {f.get('severity', '')} | {f.get('rule_id', '')} "
                    f"| {f.get('file_path', '')} | {f.get('line_start', '')} "
                    f"| {f.get('cwe', '')} |"
                )

        for tool in _SCA_TOOLS:
            sca_findings = findings.get(tool, [])
            if sca_findings:
                lines += [
                    "",
                    f"### SCA ({tool})",
                    "| Severity | Package | Version | Vulnerability ID | Fixed In |",
                    "|----------|---------|---------|-----------------|----------|",
                ]
                for f in sca_findings:
                    lines.append(
                        f"| {f.get('severity', '')} | {f.get('package_name', '')} "
                        f"| {f.get('package_version', '')} "
                        f"| {f.get('vulnerability_id', '')} "
                        f"| {f.get('fixed_version', '')} |"
                    )

        gitleaks_findings = findings.get("gitleaks", [])
        if gitleaks_findings:
            lines += [
                "",
                "### Secrets (gitleaks)",
                "| Rule | File | Line |",
                "|------|------|------|",
            ]
            for f in gitleaks_findings:
                lines.append(
                    f"| {f.get('rule_id', '')} | {f.get('file_path', '')} "
                    f"| {f.get('line_number', '')} |"
                )
            lines.append("_Note: Secret values are never stored or displayed._")

        zap_findings = findings.get("zap", [])
        if zap_findings:
            lines += [
                "",
                "### API (zap)",
                "| Severity | Alert | URL | Method | Param | CWE |",
                "|----------|-------|-----|--------|-------|-----|",
            ]
            for f in zap_findings:
                lines.append(
                    f"| {f.get('severity', '')} | {f.get('alert_name', '')} "
                    f"| {f.get('url', '')} | {f.get('method', '')} "
                    f"| {f.get('param', '')} | {f.get('cwe_id', '')} |"
                )

        noir_findings = findings.get("noir", [])
        if noir_findings:
            lines += [
                "",
                "### Discovered Attack Surface (noir)",
                "| Method | URI | Source File | Parameters |",
                "|--------|-----|-------------|------------|",
            ]
            for f in noir_findings:
                source = f.get("file") or ""
                desc = f.get("description", "")
                params = ""
                if "params:" in desc:
                    params = desc.split("params:", 1)[-1].strip()
                lines.append(
                    f"| {f.get('method', '')} | {f.get('url', '')} "
                    f"| {source} | {params} |"
                )
            lines.append(
                "_Note: Discovered Attack Surface entries are informational, "
                "not vulnerability findings._"
            )

        return "\n".join(lines)

    def _render_html(self, aggregated: dict[str, Any]) -> str:
        """Render aggregated findings as self-contained HTML with inline CSS."""
        project_name = aggregated["project_name"]
        generated_at = aggregated["generated_at"]
        summary = aggregated["summary"]
        findings = aggregated["findings"]
        by_sev = summary["by_severity"]

        css = (
            "body{font-family:Arial,sans-serif;margin:0;padding:0;background:#f3f4f6;color:#111827;}"
            ".hdr{background:#1e293b;color:#fff;padding:24px 32px;}"
            ".hdr h1{margin:0;font-size:1.5em;}"
            ".hdr p{margin:4px 0 0;font-size:.9em;color:#94a3b8;}"
            ".wrap{padding:24px 32px;}"
            ".summary{background:#fff;border-radius:8px;"
            "padding:16px 24px;margin-bottom:24px;"
            "box-shadow:0 1px 3px rgba(0,0,0,.1);}"
            ".summary h2{margin-top:0;font-size:1.1em;color:#374151;}"
            ".badges{display:flex;gap:12px;flex-wrap:wrap;}"
            ".badge{padding:6px 14px;border-radius:6px;"
            "color:#fff;font-weight:bold;font-size:.9em;}"
            ".badge.total{background:#374151;}.badge.critical{background:#dc2626;}"
            ".badge.high{background:#ea580c;}.badge.medium{background:#ca8a04;}"
            ".badge.low{background:#2563eb;}"
            ".section{background:#fff;border-radius:8px;"
            "padding:16px 24px;margin-bottom:20px;"
            "box-shadow:0 1px 3px rgba(0,0,0,.1);}"
            ".section h3{margin-top:0;color:#1e40af;}"
            "table{width:100%;border-collapse:collapse;font-size:.9em;}"
            "th{background:#f8fafc;text-align:left;padding:8px 12px;"
            "border-bottom:2px solid #e2e8f0;}"
            "td{padding:7px 12px;border-bottom:1px solid #f1f5f9;}"
            "tr:hover td{background:#f8fafc;}"
            ".sev{padding:2px 6px;border-radius:3px;"
            "font-size:.85em;color:#fff;font-weight:bold;}"
            ".sev-critical{background:#dc2626;}.sev-high{background:#ea580c;}"
            ".sev-medium{background:#ca8a04;}.sev-low{background:#2563eb;}"
            ".note{font-size:.85em;color:#6b7280;margin-top:8px;}"
        )

        def sev_badge(sev: str) -> str:
            cls = (
                f"sev sev-{sev.lower()}"
                if sev.lower() in ("critical", "high", "medium", "low")
                else "sev"
            )
            return f'<span class="{cls}">{sev}</span>'

        def th(*cols: str) -> str:
            return (
                "<thead><tr>" + "".join(f"<th>{c}</th>" for c in cols) + "</tr></thead>"
            )

        def tr(*cells: str) -> str:
            return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"

        sections: list[str] = []

        semgrep_findings = findings.get("semgrep", [])
        if semgrep_findings:
            rows = "".join(
                tr(
                    sev_badge(f.get("severity", "")),
                    f.get("rule_id", ""),
                    f.get("file_path", ""),
                    str(f.get("line_start", "")),
                    f.get("cwe", ""),
                )
                for f in semgrep_findings
            )
            sections.append(
                f'<div class="section"><h3>SAST (semgrep)</h3>'
                f"<table>{th('Severity', 'Rule', 'File', 'Line', 'CWE')}"
                f"<tbody>{rows}</tbody></table></div>"
            )

        for tool in _SCA_TOOLS:
            sca_findings = findings.get(tool, [])
            if sca_findings:
                rows = "".join(
                    tr(
                        sev_badge(f.get("severity", "")),
                        f.get("package_name", ""),
                        f.get("package_version", ""),
                        f.get("vulnerability_id", ""),
                        f.get("fixed_version", ""),
                    )
                    for f in sca_findings
                )
                _th = th(
                    "Severity", "Package", "Version", "Vulnerability ID", "Fixed In"
                )
                sections.append(
                    f'<div class="section"><h3>SCA ({tool})</h3>'
                    f"<table>{_th}"
                    f"<tbody>{rows}</tbody></table></div>"
                )

        gitleaks_findings = findings.get("gitleaks", [])
        if gitleaks_findings:
            rows = "".join(
                tr(
                    f.get("rule_id", ""),
                    f.get("file_path", ""),
                    str(f.get("line_number", "")),
                )
                for f in gitleaks_findings
            )
            sections.append(
                f'<div class="section"><h3>Secrets (gitleaks)</h3>'
                f"<table>{th('Rule', 'File', 'Line')}"
                f"<tbody>{rows}</tbody></table>"
                '<p class="note">Note: Secret values are never'
                " stored or displayed.</p></div>"
            )

        zap_findings = findings.get("zap", [])
        if zap_findings:
            rows = "".join(
                tr(
                    sev_badge(f.get("severity", "")),
                    f.get("alert_name", ""),
                    f.get("url", ""),
                    f.get("method", ""),
                    f.get("param", ""),
                    str(f.get("cwe_id", "")),
                )
                for f in zap_findings
            )
            sections.append(
                f'<div class="section"><h3>API (zap)</h3>'
                f"<table>{th('Severity', 'Alert', 'URL', 'Method', 'Param', 'CWE')}"
                f"<tbody>{rows}</tbody></table></div>"
            )

        noir_findings = findings.get("noir", [])
        if noir_findings:
            rows = "".join(
                tr(
                    f.get("method", ""),
                    f.get("url", ""),
                    f.get("file") or "",
                    (
                        f.get("description", "").split("params:", 1)[-1].strip()
                        if "params:" in f.get("description", "")
                        else ""
                    ),
                )
                for f in noir_findings
            )
            sections.append(
                '<div class="section">'
                "<h3>Discovered Attack Surface (noir)</h3>"
                f"<table>{th('Method', 'URI', 'Source File', 'Parameters')}"
                f"<tbody>{rows}</tbody></table>"
                '<p class="note">Note: Discovered Attack Surface entries are'
                " informational, not vulnerability findings.</p></div>"
            )

        if not sections:
            sections.append(
                '<div class="section"><p><em>No findings ingested yet.</em></p></div>'
            )

        sections_html = "\n".join(sections)
        return (
            f'<!DOCTYPE html>\n<html lang="en">\n'
            f'<head><meta charset="UTF-8">'
            f"<title>Tally Security Report: {project_name}</title>"
            f"<style>{css}</style></head>\n"
            f"<body>\n"
            f'<div class="hdr"><h1>Tally Security Report: {project_name}</h1>'
            f"<p>Generated: {generated_at}</p></div>\n"
            f'<div class="wrap">\n'
            f'<div class="summary"><h2>Executive Summary</h2>'
            f'<div class="badges">'
            f'<span class="badge total">Total: {summary["total_findings"]}</span>'
            f'<span class="badge critical">Critical: {by_sev.get("critical", 0)}</span>'
            f'<span class="badge high">High: {by_sev.get("high", 0)}</span>'
            f'<span class="badge medium">Medium: {by_sev.get("medium", 0)}</span>'
            f'<span class="badge low">Low: {by_sev.get("low", 0)}</span>'
            f"</div></div>\n"
            f"{sections_html}\n"
            f"</div>\n</body>\n</html>"
        )

    def _render_json(self, aggregated: dict[str, Any]) -> str:
        """Return aggregated findings as JSON."""
        return json.dumps(aggregated, indent=2)
