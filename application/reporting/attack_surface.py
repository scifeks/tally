"""Attack Surface Overview builder — three HTML recon tables for the report."""

from __future__ import annotations

import html
import json
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort

logger = logging.getLogger(__name__)

# Tool names that belong to the SCA category.
_SCA_TOOLS: frozenset[str] = frozenset(
    {"osv-scanner", "pip-audit", "npm-audit", "composer-audit"}
)

# Segment values and their display column headers for the repo surface table.
_SEGMENT_COLUMNS: list[tuple[str, str]] = [
    ("sast", "SAST"),
    ("secrets", "Secrets"),
    ("sca", "SCA"),
    ("dast", "DAST"),
]

_PRESENT = "&#x2713;"  # ✓
_ABSENT = "&#x2014;"  # —

# Shared scoped styles injected once at the top of the combined HTML block.
_STYLES = (
    "<style>"
    ".tally-surface{font-family:Arial,sans-serif;margin-bottom:24px;}"
    ".tally-surface h3{font-size:1em;font-weight:bold;margin:16px 0 6px;color:#1a1a2e;}"
    ".tally-surface table{border-collapse:collapse;width:100%;font-size:.85em;}"
    ".tally-surface th{background:#1a1a2e;color:#fff;padding:6px 10px;"
    "text-align:left;white-space:nowrap;}"
    ".tally-surface td{padding:5px 10px;border-bottom:1px solid #e5e7eb;"
    "vertical-align:top;}"
    ".tally-surface tr:nth-child(even) td{background:#f9fafb;}"
    ".tally-surface .host-header td{background:#eef2ff;font-weight:bold;"
    "color:#1a1a2e;padding:6px 10px;}"
    ".tally-surface .present{color:#27ae60;font-weight:bold;text-align:center;}"
    ".tally-surface .absent{color:#9ca3af;text-align:center;}"
    ".tally-surface .notice{color:#6b7280;font-style:italic;margin:6px 0;}"
    "</style>"
)


def _parse_meta(finding: dict[str, Any]) -> dict[str, Any]:
    """Parse the meta JSON blob; return empty dict on failure."""
    meta = finding.get("meta")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


class AttackSurfaceBuilder:
    """Builds the Attack Surface Overview HTML block for the report.

    Two subsections:
    - Repository Surface — which tool categories ran against each repo
    - Dependency Surface — which ecosystems were audited per repo
    """

    def __init__(self, finding_repo: FindingRepositoryPort) -> None:
        self._repo = finding_repo

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def build(self, filtered_findings: list[dict[str, Any]]) -> str:
        """Return the full Attack Surface Overview HTML fragment.

        Args:
            filtered_findings: Pre-filtered findings (triaged, should_report=1).
                               Used for Repository and Dependency surfaces.

        Returns:
            Self-contained HTML fragment including scoped ``<style>`` block.
        """
        repo_html = self._build_repository_surface(filtered_findings)
        dep_html = self._build_dependency_surface(filtered_findings)

        return (
            _STYLES
            + '<div class="tally-surface">'
            + "<h3>Repository Surface</h3>"
            + repo_html
            + "<h3>Dependency Surface</h3>"
            + dep_html
            + "</div>"
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _build_repository_surface(self, findings: list[dict[str, Any]]) -> str:
        """Render a repo × tool-category coverage matrix.

        Rows are repositories; columns are SAST, Secrets, SCA, DAST.
        A ✓ appears where at least one finding from that category was found
        for the repo.  NULL repo values are grouped under "Unattributed".
        """
        if not findings:
            return (
                '<p class="notice">'
                "No triaged findings available for repository surface analysis."
                "</p>"
            )

        # Build set of segments present per repo.
        repo_segments: dict[str, set[str]] = defaultdict(set)
        for f in findings:
            repo = (f.get("repo") or "").strip() or "Unattributed"
            seg = (f.get("segment") or "").lower().strip()
            if seg:
                repo_segments[repo].add(seg)

        if not repo_segments:
            return '<p class="notice">No repository surface data available.</p>'

        col_keys = [k for k, _ in _SEGMENT_COLUMNS]
        col_labels = [lbl for _, lbl in _SEGMENT_COLUMNS]

        header_cells = "".join(f"<th>{lbl}</th>" for lbl in col_labels)
        rows_html: list[str] = []
        for repo in sorted(repo_segments):
            present_segs = repo_segments[repo]
            cells = "".join(
                (
                    f'<td class="present">{_PRESENT}</td>'
                    if col in present_segs
                    else f'<td class="absent">{_ABSENT}</td>'
                )
                for col in col_keys
            )
            rows_html.append(f"<tr><td>{html.escape(repo)}</td>{cells}</tr>")

        return (
            "<table>"
            "<thead><tr>"
            f"<th>Repository</th>{header_cells}"
            "</tr></thead>"
            "<tbody>" + "".join(rows_html) + "</tbody></table>"
        )

    def _build_dependency_surface(self, findings: list[dict[str, Any]]) -> str:
        """Render a table of audited dependency ecosystems per repository.

        One row per distinct (repo, ecosystem) pair from SCA findings.
        """
        sca = [f for f in findings if (f.get("tool") or "").lower() in _SCA_TOOLS]

        if not sca:
            return (
                '<p class="notice">'
                "Dependency scanning data is not available for this project."
                "</p>"
            )

        seen: set[tuple[str, str]] = set()
        pairs: list[tuple[str, str]] = []
        for f in sca:
            repo = (f.get("repo") or "").strip() or "Unattributed"
            ecosystem = (f.get("ecosystem") or "").strip()
            if not ecosystem:
                continue
            key = (repo, ecosystem)
            if key not in seen:
                seen.add(key)
                pairs.append(key)

        if not pairs:
            return (
                '<p class="notice">'
                "No ecosystem data found in dependency scan findings."
                "</p>"
            )

        pairs.sort()
        rows_html = "".join(
            f"<tr><td>{html.escape(repo)}</td><td>{html.escape(ecosystem)}</td></tr>"
            for repo, ecosystem in pairs
        )
        return (
            "<table>"
            "<thead><tr><th>Repository</th><th>Ecosystem</th></tr></thead>"
            "<tbody>" + rows_html + "</tbody></table>"
        )


__all__ = ["AttackSurfaceBuilder"]
