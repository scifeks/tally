"""Shared query utilities for report draft generation."""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

if TYPE_CHECKING:
    from infrastructure.store.repositories.findings import FindingRepository

from application.reporting.risk_level import RiskCounts

logger = logging.getLogger(__name__)

_SEVERITY_ORDER: dict[str, int] = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "informational": 4,
}
_CONFIDENCE_ORDER: dict[str, int] = {
    "confirmed": 0,
    "probable": 1,
    "potential": 2,
}


class DraftQueryService:
    """Queries and aggregates filtered findings for report draft generation."""

    def __init__(self, finding_repo: FindingRepository) -> None:
        self._repo = finding_repo

    def get_filtered_findings(self, skip_triage: bool = False) -> list[dict[str, Any]]:
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

    def severity_distribution(self, findings: list[dict[str, Any]]) -> dict[str, int]:
        """Return count per severity tier."""
        dist: dict[str, int] = {
            s: 0 for s in ("critical", "high", "medium", "low", "informational")
        }
        for f in findings:
            sev = (f.get("severity") or "").lower()
            if sev in dist:
                dist[sev] += 1
        return dist

    def confidence_distribution(self, findings: list[dict[str, Any]]) -> dict[str, int]:
        """Return count per confidence level."""
        dist: dict[str, int] = {c: 0 for c in ("confirmed", "probable", "potential")}
        for f in findings:
            conf = (f.get("confidence") or "").lower()
            if conf in dist:
                dist[conf] += 1
        return dist

    def build_risk_counts(self, findings: list[dict[str, Any]]) -> RiskCounts:
        """Derive RiskCounts from the filtered findings list."""
        n_conf_crit = sum(
            1
            for f in findings
            if (f.get("severity") or "").lower() == "critical"
            and (f.get("confidence") or "").lower() == "confirmed"
        )
        n_conf_high = sum(
            1
            for f in findings
            if (f.get("severity") or "").lower() == "high"
            and (f.get("confidence") or "").lower() == "confirmed"
        )
        n_prob_conf_medium = sum(
            1
            for f in findings
            if (f.get("severity") or "").lower() == "medium"
            and (f.get("confidence") or "").lower() in ("confirmed", "probable")
        )
        n_low = sum(1 for f in findings if (f.get("severity") or "").lower() == "low")
        n_recurring = sum(1 for f in findings if (f.get("seen_count") or 0) > 1)
        return RiskCounts(
            confirmed_critical=n_conf_crit,
            confirmed_high=n_conf_high,
            prob_confirmed_medium=n_prob_conf_medium,
            low_total=n_low,
            recurring=n_recurring,
        )

    def top_findings(
        self, findings: list[dict[str, Any]], n: int = 5
    ) -> list[dict[str, Any]]:
        """Return top N findings sorted by severity then confidence.

        If fewer than 3 confirmed/probable critical-or-high findings exist,
        lower-severity findings are included to reach n total.
        """

        def _sort_key(f: dict[str, Any]) -> tuple[int, int]:
            sev = _SEVERITY_ORDER.get((f.get("severity") or "").lower(), 99)
            conf = _CONFIDENCE_ORDER.get((f.get("confidence") or "").lower(), 99)
            return (sev, conf)

        return sorted(findings, key=_sort_key)[:n]

    def risk_type_groups(
        self, findings: list[dict[str, Any]], top_n: int = 8
    ) -> list[tuple[str, int]]:
        """Return top_n (risk_type, count) pairs derived from meta blobs."""
        counts: Counter[str] = Counter()
        for f in findings:
            meta = _parse_meta(f)
            rt = meta.get("risk_type")
            if rt and isinstance(rt, str) and rt.strip():
                counts[rt.strip()] += 1
        return counts.most_common(top_n)

    def distinct_tools(self, findings: list[dict[str, Any]]) -> list[str]:
        """Return sorted list of distinct tool names."""
        return sorted(
            {(f.get("tool") or "").strip() for f in findings if f.get("tool")}
        )

    def distinct_repos(self, findings: list[dict[str, Any]]) -> list[str]:
        """Return sorted list of distinct repo names."""
        return sorted(
            {(f.get("repo") or "").strip() for f in findings if f.get("repo")}
        )

    def distinct_url_hosts(self, findings: list[dict[str, Any]]) -> list[str]:
        """Extract distinct host:port values from ZAP findings' url column."""
        zap = [f for f in findings if (f.get("tool") or "").lower() == "zap"]
        hosts: set[str] = set()
        for f in zap:
            url = f.get("url") or ""
            if url:
                try:
                    netloc = urlparse(url).netloc
                    if netloc:
                        hosts.add(netloc)
                except Exception:
                    pass
        return sorted(hosts)

    def distinct_ecosystems(self, findings: list[dict[str, Any]]) -> list[str]:
        """Extract distinct ecosystem values from SCA findings."""
        _sca = frozenset({"osv-scanner", "pip-audit", "npm-audit", "composer-audit"})
        sca = [f for f in findings if (f.get("tool") or "").lower() in _sca]
        return sorted(
            {(f.get("ecosystem") or "").strip() for f in sca if f.get("ecosystem")}
        )

    def recurring_findings(
        self, findings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Return findings with seen_count > 1."""
        return [f for f in findings if (f.get("seen_count") or 0) > 1]

    def recurring_by_risk_type(
        self, findings: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group recurring findings by risk_type from the meta blob."""
        recurring = self.recurring_findings(findings)
        groups: dict[str, list[dict[str, Any]]] = {}
        for f in recurring:
            meta = _parse_meta(f)
            rt = (meta.get("risk_type") or "unclassified").strip()
            groups.setdefault(rt, []).append(f)
        return groups


def _parse_meta(finding: dict[str, Any]) -> dict[str, Any]:
    """Parse the meta JSON blob from a finding row."""
    meta = finding.get("meta")
    if isinstance(meta, dict):
        return meta
    if isinstance(meta, str):
        try:
            return json.loads(meta)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}
