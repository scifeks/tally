"""Parser and handler for garak LLM vulnerability scanner."""

import json
from pathlib import Path
from typing import Any

from domain.tools.base import ToolResult
from domain.tools.constants import OWASP_LLM_CODE_TO_NAME
from domain.tools.enrichment import FieldEnrichmentSpec, PromptStrategy

from ._shared import _first_output_file, _shared_meta


def parse_garak_report(report_path: Path) -> dict[str, Any]:
    try:
        with open(report_path, encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"Parse error: {exc}"}
    return _parse_garak_data(lines)


def _parse_garak_data(lines: list[dict[str, Any]]) -> dict[str, Any]:
    probe_meta, detector_meta = _extract_plugin_cache(lines)
    findings = _extract_failed_evals(lines, probe_meta, detector_meta)

    return {
        "findings": findings,
        "summary": {"total_findings": len(findings)},
    }


def _extract_plugin_cache(
    lines: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    probe_meta: dict[str, Any] = {}
    detector_meta: dict[str, Any] = {}

    for line in lines:
        if line.get("entry_type") != "plugin_cache":
            continue
        cache = line.get("plugin_cache", {})
        probes = cache.get("probes", {})
        detectors = cache.get("detectors", {})

        for key, value in probes.items():
            probe_name = key.replace("probes.", "")
            probe_meta[probe_name] = value

        for key, value in detectors.items():
            detector_name = key.replace("detectors.", "")
            detector_meta[detector_name] = value

        break

    return probe_meta, detector_meta


def _extract_failed_evals(
    lines: list[dict[str, Any]],
    probe_meta: dict[str, Any],
    detector_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for line in lines:
        if line.get("entry_type") != "eval":
            continue

        fails = line.get("fails", 0)
        if fails == 0:
            continue

        probe_name = line.get("probe", "")
        detector_name = line.get("detector", "")

        probe = probe_meta.get(probe_name, {})
        detector = detector_meta.get(detector_name, {})

        tags: list[str] = probe.get("tags", [])
        owasp_names = _resolve_owasp(tags)

        total = line.get("total_evaluated", 1)
        fail_rate = fails / total if total > 0 else 0
        confidence = _fail_rate_to_confidence(fails, total)
        severity = _tier_to_severity(probe.get("tier", 3))

        finding: dict[str, Any] = {
            "probe": probe_name,
            "detector": detector_name,
            "probe_description": probe.get("description", ""),
            "goal": probe.get("goal", ""),
            "probe_tier": probe.get("tier", 0),
            "tags": tags,
            "detector_hit_desc": detector.get("hit_desc", ""),
            "fails": fails,
            "total_evaluated": total,
            "fail_rate": fail_rate,
            "severity": severity,
            "confidence": confidence,
            "fingerprint": f"garak|{probe_name}|{detector_name}",
        }

        if owasp_names:
            finding["owasp_name"] = owasp_names

        findings.append(finding)

    return findings


def _fail_rate_to_confidence(fails: int, total: int) -> str:
    if total == 0:
        return "potential"
    rate = fails / total
    if rate >= 0.5:
        return "confirmed"
    if rate >= 0.2:
        return "probable"
    return "potential"


def _tier_to_severity(tier: int) -> str:
    tier_map = {1: "high", 2: "medium", 3: "low"}
    return tier_map.get(tier, "low")


def _resolve_owasp(tags: list[str]) -> str:
    owasp_codes = [
        tag.replace("owasp:", "") for tag in tags if tag.startswith("owasp:")
    ]
    names: list[str] = []
    for code in owasp_codes:
        name = OWASP_LLM_CODE_TO_NAME.get(code)
        if name:
            names.append(name)
    return json.dumps(names) if names else ""


class GarakHandler:
    tool_name = "garak"
    domain = "web"
    segment = "llm"
    should_enrich = True
    should_visualize = True
    non_enriched_fields: frozenset[str] = frozenset({"owasp_name"})
    type_flags: dict[str, set[str]] = {"vulnerability": {"type_vulnerability"}}
    normalized_fields: list[str] = [
        "confidence",
        "domain",
        "finding_type",
        "fingerprint",
        "probe",
        "severity",
        "tool",
    ]
    enrichment_fields: tuple[FieldEnrichmentSpec, ...] = (
        FieldEnrichmentSpec(
            "risk_type",
            ("probe_description", "goal", "tags"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "title",
            ("probe", "probe_description", "goal"),
            PromptStrategy.GENERIC,
        ),
        FieldEnrichmentSpec(
            "remediation",
            ("probe_description", "goal", "detector_hit_desc"),
            PromptStrategy.GENERIC,
        ),
    )

    def normalize(self, result: ToolResult, profile: str) -> list[dict]:
        parsed: dict[str, Any] = result.parsed_data or {}  # type: ignore[union-attr]
        findings: list[dict[str, Any]] = parsed.get("findings", [])

        timestamp = result.timestamp
        source_file = _first_output_file(result.output_files)

        rows: list[dict] = []

        for finding in findings:
            probe = finding.get("probe", "")
            detector = finding.get("detector", "")
            severity = finding.get("severity", "low")
            confidence = finding.get("confidence", "potential")
            probe_desc = finding.get("probe_description", "")
            goal = finding.get("goal", "")
            fail_rate = finding.get("fail_rate", 0.0)
            tags: list[str] = finding.get("tags", [])
            detector_hit = finding.get("detector_hit_desc", "")
            fails = finding.get("fails", 0)
            total = finding.get("total_evaluated", 0)
            fingerprint = finding.get("fingerprint", "")
            owasp_name = finding.get("owasp_name", "")

            tags_str = ", ".join(tags) if tags else ""

            row: dict[str, Any] = {
                "tool": "garak",
                "profile": profile,
                "finding_type": json.dumps(["vulnerability"]),
                "severity": severity,
                "confidence": confidence,
                "probe": probe,
                "detector": detector,
                "fail_rate": fail_rate,
                "fails": fails,
                "total_evaluated": total,
                "timestamp": timestamp,
                "source_file": source_file,
            }

            if probe_desc:
                row["probe_description"] = probe_desc
            if goal:
                row["goal"] = goal
            if tags_str:
                row["tags"] = tags_str
            if detector_hit:
                row["detector_hit_desc"] = detector_hit
            if fingerprint:
                row["fingerprint"] = fingerprint
            if owasp_name:
                row["owasp_name"] = owasp_name
            if probe:
                row["title"] = probe

            row.update(_shared_meta(self, "vulnerability"))

            rows.append(row)

        return rows

    def render(self, row: dict) -> str:
        parts = [
            f"Probe: {row.get('probe', '')}",
            f"Detector: {row.get('detector', '')}",
            f"Severity: {row.get('severity', '')}",
            f"Confidence: {row.get('confidence', '')}",
            f"Fails: {row.get('fails', '')}/{row.get('total_evaluated', '')}",
        ]
        if row.get("probe_description"):
            parts.append(f"Description: {row['probe_description']}")
        if row.get("goal"):
            parts.append(f"Goal: {row['goal']}")
        if row.get("tags"):
            parts.append(f"Tags: {row['tags']}")
        if row.get("detector_hit_desc"):
            parts.append(f"Hit: {row['detector_hit_desc']}")
        if row.get("risk_type"):
            parts.append(f"Risk type: {row['risk_type']}")
        if row.get("title"):
            parts.append(f"Title: {row['title']}")
        if row.get("remediation"):
            parts.append(f"Remediation: {row['remediation']}")
        if row.get("owasp_name"):
            parts.append(f"OWASP: {row['owasp_name']}")
        return "[garak] " + " | ".join(parts)

    def fingerprint_key(self, finding: dict[str, Any]) -> str:
        return "|".join(
            [
                "garak",
                str(finding.get("probe", "")),
                str(finding.get("detector", "")),
            ]
        )
