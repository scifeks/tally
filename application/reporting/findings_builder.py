"""Build HTML fragments for finding tables and cards in the report."""

from __future__ import annotations

import html
import logging
from collections import defaultdict
from typing import Any

from domain.findings.severity import Severity

logger = logging.getLogger(__name__)


# Private helpers


def _parse_meta(finding: dict[str, Any]) -> dict[str, Any]:
    """Return the meta dict; defaults to empty when missing or malformed."""
    meta = finding.get("meta")
    return meta if isinstance(meta, dict) else {}


def _get_title(finding: dict[str, Any]) -> str:
    """Return a display title for the finding (HTML-escaped)."""
    meta = _parse_meta(finding)
    raw = meta.get("title") or finding.get("rule_id") or "Untitled"
    return html.escape(str(raw))


def _get_remediation(finding: dict[str, Any]) -> str:
    """Return remediation text (HTML-escaped).

    Resolution order:
      1. meta.triage.remediation (set by triage pipeline, most authoritative)
      2. meta.remediation (e.g. ZAP's 'solution' field)
      3. Fallback string
    """
    meta = _parse_meta(finding)
    triage = meta.get("triage")
    if isinstance(triage, dict):
        value = triage.get("remediation")
        if value:
            return html.escape(str(value))
    value = meta.get("remediation")
    if value:
        return html.escape(str(value))
    return "No remediation guidance available."


def _get_owasp_name(finding: dict[str, Any]) -> str:
    """Return the OWASP/classification name for the finding (HTML-escaped).

    Resolution order:
      1. meta.owasp_name
      2. First CWE from the cwe list
      3. rule_id column
      4. "Unclassified" (logs a warning)
    """
    meta = _parse_meta(finding)
    owasp = meta.get("owasp_name")
    if owasp:
        return html.escape(str(owasp))

    cwe_list = finding.get("cwe")
    if isinstance(cwe_list, list) and cwe_list:
        return html.escape(str(cwe_list[0]))

    rule_id = finding.get("rule_id")
    if rule_id:
        return html.escape(str(rule_id))

    logger.warning(
        "Finding id=%s has no owasp_name, cwe, or rule_id; using 'Unclassified'.",
        finding.get("id"),
    )
    return "Unclassified"


def _badge(css_class: str, value: str) -> str:
    """Return a styled badge span.

    The modifier class is the normalised value (lowercase, spaces → hyphens).
    The display text is HTML-escaped.
    """
    modifier = value.lower().replace(" ", "-")
    return (
        f'<span class="{html.escape(css_class)} {html.escape(modifier)}">'
        f"{html.escape(value)}</span>"
    )


def _severity_key(finding: dict[str, Any]) -> int:
    """Numeric sort key for severity (lower = more severe)."""
    try:
        return Severity.from_label((finding.get("severity") or "").lower()).rank
    except ValueError:
        return 99


def _line_number(meta: dict[str, Any]) -> str | None:
    """Extract a line number from meta, preferring line_number over line_start."""
    return meta.get("line_number") or meta.get("line_start")


def _affected_location(finding: dict[str, Any], meta: dict[str, Any]) -> str:
    """Build the affected location string for a code finding card.

    Keyed on the ``segment`` column (no tool-name checks).

    Segments:
      ``sca``: package name, version, ecosystem
      ``api``: HTTP method + URL
      ``sast``, ``secrets``: file path + line number
    """
    segment = (finding.get("segment") or "").lower()

    if segment == "sca":
        pkg = html.escape(str(finding.get("package_name") or ""))
        ver = html.escape(str(finding.get("package_version") or ""))
        eco = html.escape(str(finding.get("ecosystem") or ""))
        parts = [pkg]
        if ver:
            parts[0] = f"{pkg}@{ver}"
        if eco:
            parts.append(f"({eco})")
        return " ".join(parts) if any(parts) else "(location unavailable)"

    if segment == "api":
        method = html.escape(str(meta.get("method") or ""))
        url = html.escape(str(finding.get("url") or ""))
        return f"{method} {url}".strip() or "(location unavailable)"

    if segment in ("sast", "secrets"):
        file_path = html.escape(str(finding.get("file") or ""))
        line = _line_number(meta)
        line_str = html.escape(str(line)) if line else ""
        if file_path and line_str:
            return f"{file_path}:{line_str}"
        return file_path or "(location unavailable)"

    return "(location unavailable)"


# FindingsBuilder


class FindingsBuilder:
    """Builds HTML fragments for all Segment 5 report sections.

    Args:
        prefix: Resolved finding ID prefix (e.g. ``"TAL"``, ``"FOO"``).
                When empty, findings use a numeric-only format (e.g. ``001``).

    User-sourced values are always HTML-escaped.  CSS classes reference the
    palette defined in ``static/report.css``; no colours are hardcoded here.
    """

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    def _id_header(self) -> str:
        """Return the column header label for the finding ID column."""
        return f"{self._prefix}-ID" if self._prefix else "ID"

    # Master Findings Table

    def build_master_table(
        self,
        code_findings: list[dict[str, Any]],
    ) -> str:
        """Return HTML for the Master Findings Table.

        The ``<h2>`` heading is included in the returned HTML (the template
        does not provide headings for this slot).

        Args:
            code_findings: Pre-sorted, finding-ID-assigned findings.

        Returns:
            HTML string of the findings table.
        """
        parts: list[str] = []

        # --- Code findings ---
        parts.append("<h2>Code Findings</h2>")
        if not code_findings:
            parts.append('<p class="placeholder">No code findings to display.</p>')
        else:
            parts.append("<table>")
            parts.append(
                "<thead><tr>"
                f"<th>{self._id_header()}</th><th>Title</th>"
                "<th>Severity</th><th>Status</th><th>Confidence</th>"
                "</tr></thead><tbody>"
            )
            for f in code_findings:
                recurring = (f.get("seen_count") or 0) > 1
                row_class = ' class="recurring-row"' if recurring else ""
                tal_id = html.escape(str(f.get("tal_id") or "-"))
                title = _get_title(f)
                sev = (f.get("severity") or "").lower()
                status = (f.get("status") or "active").lower()
                conf = (f.get("confidence") or "").lower()
                parts.append(
                    f"<tr{row_class}>"
                    f"<td>{tal_id}</td>"
                    f"<td>{title}</td>"
                    f"<td>{_badge('severity-badge', sev)}</td>"
                    f"<td>{_badge('status-badge', status)}</td>"
                    f"<td>{_badge('confidence-badge', conf)}</td>"
                    "</tr>"
                )
            parts.append("</tbody></table>")

        return "\n".join(parts)

    # Code Finding Cards

    @staticmethod
    def build_code_cards(code_findings: list[dict[str, Any]]) -> str:
        """Return HTML for per-finding detail cards grouped by repo.

        Args:
            code_findings: Pre-sorted, finding-ID-assigned non-network findings.

        Returns:
            HTML string of grouped finding cards.
        """
        if not code_findings:
            return '<p class="placeholder">No code findings to display.</p>'

        # Group by repo; None → "Unattributed".
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in code_findings:
            key = f.get("repo") or "Unattributed"
            groups[key].append(f)

        parts: list[str] = []
        for repo_name in sorted(groups):
            parts.append(f"<h3>{html.escape(repo_name)}</h3>")
            # Sort within group by severity desc.
            repo_findings = sorted(groups[repo_name], key=_severity_key)
            for f in repo_findings:
                meta = _parse_meta(f)
                tal_id = html.escape(str(f.get("tal_id") or "-"))
                title = _get_title(f)
                sev = (f.get("severity") or "").lower()
                conf = (f.get("confidence") or "").lower()
                status = (f.get("status") or "active").lower()
                desc = html.escape(
                    str(f.get("description") or "No description available.")
                )
                remediation = _get_remediation(f)
                location = _affected_location(f, meta)

                parts.append(
                    '<div class="finding-card">'
                    '<div class="finding-card-header">'
                    f'<span class="finding-id">{tal_id}</span>'
                    f'<span class="finding-title">{title}</span>'
                    f"{_badge('severity-badge', sev)}"
                    f"{_badge('confidence-badge', conf)}"
                    f"{_badge('status-badge', status)}"
                    "</div>"
                    '<div class="finding-card-body">'
                    f"<p><strong>Description:</strong> {desc}</p>"
                    f"<p><strong>Remediation:</strong> {remediation}</p>"
                    f"<p><strong>Affected Location:</strong> {location}</p>"
                    "</div>"
                    "</div>"
                )

        return "\n".join(parts)

    # Secrets Cards

    @staticmethod
    def build_secrets_cards(secrets_findings: list[dict[str, Any]]) -> str:
        """Return HTML for per-repo secrets summary cards.

        Receives findings already filtered to ``segment == "secrets"`` by the
        assembler.  No secret values or line numbers are included.

        Args:
            secrets_findings: Findings with segment ``"secrets"``.

        Returns:
            HTML string of per-repo summary cards.
        """
        if not secrets_findings:
            return '<p class="placeholder">No secrets findings detected.</p>'

        # Group by repo; None → "Unattributed".
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for f in secrets_findings:
            key = f.get("repo") or "Unattributed"
            groups[key].append(f)

        parts: list[str] = []
        for repo_name in sorted(groups):
            repo_findings = groups[repo_name]
            total = len(repo_findings)

            # Count by rule_id.
            rule_counts: dict[str, int] = defaultdict(int)
            for f in repo_findings:
                rule_counts[f.get("rule_id") or "(unknown rule)"] += 1

            # Unique file paths (no line numbers, no secret values).
            file_paths: set[str] = {f["file"] for f in repo_findings if f.get("file")}

            parts.append(
                '<div class="finding-card">'
                f"<h3>{html.escape(repo_name)}</h3>"
                f"<p>Total secrets detected: <strong>{total}</strong></p>"
                "<table>"
                "<thead><tr><th>Secret Type (Rule)</th><th>Count</th></tr></thead>"
                "<tbody>"
            )
            for rule_id, count in sorted(rule_counts.items(), key=lambda kv: -kv[1]):
                parts.append(
                    f"<tr><td>{html.escape(rule_id)}</td><td>{count}</td></tr>"
                )
            parts.append("</tbody></table>")

            if file_paths:
                parts.append("<p><strong>Affected files:</strong></p><ul>")
                for fp in sorted(file_paths):
                    parts.append(f"<li><code>{html.escape(fp)}</code></li>")
                parts.append("</ul>")

            parts.append("</div>")

        return "\n".join(parts)

    # Comprehensive Code Findings (Appendix)

    def build_comprehensive_code_table(
        self, code_findings: list[dict[str, Any]]
    ) -> str:
        """Return HTML for the comprehensive code findings appendix table.

        Columns: Finding ID | OWASP Name | Severity | Confidence | Repo | File Path
        | Line Number.

        Args:
            code_findings: Pre-sorted, finding-ID-assigned non-network findings.

        Returns:
            HTML string of the detail table.
        """
        if not code_findings:
            return '<p class="placeholder">No code findings available.</p>'

        # Sort by severity desc, then repo alpha (stable).
        sorted_findings = sorted(
            code_findings,
            key=lambda f: (
                _severity_key(f),
                (f.get("repo") or "").lower(),
            ),
        )

        parts: list[str] = [
            "<table>",
            "<thead><tr>"
            f"<th>{self._id_header()}</th><th>OWASP Name</th><th>Severity</th>"
            "<th>Confidence</th><th>Repo</th><th>File Path</th><th>Line</th>"
            "</tr></thead><tbody>",
        ]
        for f in sorted_findings:
            meta = _parse_meta(f)
            tal_id = html.escape(str(f.get("tal_id") or "-"))
            owasp = _get_owasp_name(f)
            sev = (f.get("severity") or "").lower()
            conf = (f.get("confidence") or "").lower()
            repo = html.escape(str(f.get("repo") or "Unattributed"))
            file_path = html.escape(str(f.get("file") or "-"))
            line = _line_number(meta)
            line_str = html.escape(str(line)) if line else "-"

            parts.append(
                f"<tr>"
                f"<td>{tal_id}</td>"
                f"<td>{owasp}</td>"
                f"<td>{_badge('severity-badge', sev)}</td>"
                f"<td>{_badge('confidence-badge', conf)}</td>"
                f"<td>{repo}</td>"
                f"<td>{file_path}</td>"
                f"<td>{line_str}</td>"
                "</tr>"
            )
        parts.append("</tbody></table>")
        return "\n".join(parts)

    # Internal helpers


__all__ = ["FindingsBuilder"]
