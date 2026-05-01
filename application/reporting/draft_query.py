"""Shared query utilities for report draft generation."""

from __future__ import annotations

import logging
from collections import Counter
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from application.ports.finding_repository import FindingRepositoryPort
    from domain.findings.entry import Finding

from application.reporting.risk_level import RiskCounts
from domain.findings.severity import Severity

logger = logging.getLogger(__name__)

_CONFIDENCE_ORDER: dict[str, int] = {
    "confirmed": 0,
    "probable": 1,
    "potential": 2,
}


class DraftQueryService:
    """Queries and aggregates filtered findings for report draft generation."""

    def __init__(self, finding_repo: FindingRepositoryPort) -> None:
        self._repo = finding_repo

    def get_filtered_findings(self, skip_triage: bool = False) -> list[Finding]:
        """Return findings eligible for report generation.

        When *skip_triage* is False (default), only findings that have been
        triaged (``triaged_by IS NOT NULL``) and marked for inclusion
        (``should_report = 1``) are returned.

        When *skip_triage* is True, all findings are returned regardless of
        triage status — useful for generating drafts before triage is run.

        FALSE POSITIVE FILTER WIRING POINT:
        When a mechanism for flagging false positives is defined, apply the
        filter here before returning. e.g.:
            findings = [f for f in findings if not _is_false_positive(f)]
        """
        if skip_triage:
            return self._repo.get_all_findings()
        return self._repo.get_reportable_findings()

    def get_findings_for_report(self, skip_triage: bool = False) -> list[Finding]:
        """Return findings eligible for inclusion in a generated report.

        ``should_report = 1`` is always required. ``skip_triage`` only
        relaxes the requirement for non-null triage columns:

        * ``skip_triage=False`` — triaged_by IS NOT NULL AND should_report = 1
        * ``skip_triage=True``  — should_report = 1 (triage columns ignored)

        Distinct from :meth:`get_filtered_findings`, which is used by the
        LLM draft path and intentionally returns all findings when
        ``skip_triage=True`` because drafts run before triage sets
        ``should_report``.
        """
        if skip_triage:
            return self._repo.get_findings_marked_for_report()
        return self._repo.get_reportable_findings()

    def severity_distribution(self, findings: list[Finding]) -> dict[str, int]:
        """Return count per severity tier."""
        dist: dict[str, int] = {
            s: 0 for s in ("critical", "high", "medium", "low", "informational")
        }
        for f in findings:
            sev = (f.severity or "").lower()
            if sev in dist:
                dist[sev] += 1
        return dist

    def confidence_distribution(self, findings: list[Finding]) -> dict[str, int]:
        """Return count per confidence level."""
        dist: dict[str, int] = {c: 0 for c in ("confirmed", "probable", "potential")}
        for f in findings:
            conf = (f.confidence or "").lower()
            if conf in dist:
                dist[conf] += 1
        return dist

    def build_risk_counts(self, findings: list[Finding]) -> RiskCounts:
        """Derive RiskCounts from the filtered findings list."""
        n_conf_crit = sum(
            1
            for f in findings
            if (f.severity or "").lower() == "critical"
            and (f.confidence or "").lower() == "confirmed"
        )
        n_conf_high = sum(
            1
            for f in findings
            if (f.severity or "").lower() == "high"
            and (f.confidence or "").lower() == "confirmed"
        )
        n_prob_conf_medium = sum(
            1
            for f in findings
            if (f.severity or "").lower() == "medium"
            and (f.confidence or "").lower() in ("confirmed", "probable")
        )
        n_low = sum(1 for f in findings if (f.severity or "").lower() == "low")
        n_recurring = sum(1 for f in findings if (f.seen_count or 0) > 1)
        return RiskCounts(
            confirmed_critical=n_conf_crit,
            confirmed_high=n_conf_high,
            prob_confirmed_medium=n_prob_conf_medium,
            low_total=n_low,
            recurring=n_recurring,
        )

    def top_findings(self, findings: list[Finding], n: int = 5) -> list[Finding]:
        """Return top N findings sorted by severity then confidence.

        If fewer than 3 confirmed/probable critical-or-high findings exist,
        lower-severity findings are included to reach n total.
        """

        def _sort_key(f: Finding) -> tuple[int, int]:
            try:
                sev = Severity.from_label((f.severity or "").lower()).rank
            except ValueError:
                sev = 99
            conf = _CONFIDENCE_ORDER.get((f.confidence or "").lower(), 99)
            return (sev, conf)

        return sorted(findings, key=_sort_key)[:n]

    def risk_type_groups(
        self, findings: list[Finding], top_n: int = 8
    ) -> list[tuple[str, int]]:
        """Return top_n (risk_type, count) pairs derived from meta blobs."""
        counts: Counter[str] = Counter()
        for f in findings:
            rt = f.meta.get("risk_type")
            if rt and isinstance(rt, str) and rt.strip():
                counts[rt.strip()] += 1
        return counts.most_common(top_n)

    def distinct_tools(self, findings: list[Finding]) -> list[str]:
        """Return sorted list of distinct tool names."""
        return sorted({(f.tool or "").strip() for f in findings if f.tool})

    def distinct_repos(self, findings: list[Finding]) -> list[str]:
        """Return sorted list of distinct repo names from finding meta blobs."""
        return sorted(
            {
                (f.meta.get("repo") or "").strip()
                for f in findings
                if isinstance(f.meta.get("repo"), str) and f.meta.get("repo")
            }
        )

    def distinct_url_hosts(self, findings: list[Finding]) -> list[str]:
        """Extract distinct host:port values from ZAP findings' url column."""
        zap = [f for f in findings if (f.tool or "").lower() == "zap"]
        hosts: set[str] = set()
        for f in zap:
            url = f.url or ""
            if url:
                try:
                    netloc = urlparse(url).netloc
                    if netloc:
                        hosts.add(netloc)
                except Exception:
                    pass
        return sorted(hosts)

    def distinct_ecosystems(self, findings: list[Finding]) -> list[str]:
        """Extract distinct ecosystem values from SCA findings."""
        _sca = frozenset({"osv-scanner", "pip-audit", "npm-audit", "composer-audit"})
        sca = [f for f in findings if (f.tool or "").lower() in _sca]
        return sorted({(f.ecosystem or "").strip() for f in sca if f.ecosystem})

    def recurring_findings(self, findings: list[Finding]) -> list[Finding]:
        """Return findings with seen_count > 1."""
        return [f for f in findings if (f.seen_count or 0) > 1]

    def recurring_by_risk_type(
        self, findings: list[Finding]
    ) -> dict[str, list[Finding]]:
        """Group recurring findings by risk_type from the meta blob."""
        recurring = self.recurring_findings(findings)
        groups: dict[str, list[Finding]] = {}
        for f in recurring:
            rt_raw = f.meta.get("risk_type")
            rt = (rt_raw if isinstance(rt_raw, str) else "").strip() or "unclassified"
            groups.setdefault(rt, []).append(f)
        return groups
