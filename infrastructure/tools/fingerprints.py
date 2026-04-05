"""Fingerprint key functions for deduplication of findings in the SQLite store.

Each function takes a finding metadata dict and returns a stable string key.
``FINGERPRINT_REGISTRY`` maps tool name → fingerprint key function.

Used by ``infrastructure/store/repositories/findings_serial.py``.
Do NOT import from ``application/`` in this file.
"""

from __future__ import annotations

from typing import Any


def _gitleaks_fingerprint_key(finding: dict[str, Any]) -> str:
    return "|".join(
        [
            "gitleaks",
            str(finding.get("rule_id", "")),
            str(finding.get("file_path", "")),
            str(finding.get("line_number", "")),
        ]
    )


def _semgrep_fingerprint_key(finding: dict[str, Any]) -> str:
    return "|".join(
        [
            "semgrep",
            str(finding.get("rule_id", "")),
            str(finding.get("file_path", "")),
            str(finding.get("line_start", "")),
        ]
    )


def _zap_fingerprint_key(finding: dict[str, Any]) -> str:
    return "|".join(
        [
            "zap",
            str(finding.get("url", "")),
            str(finding.get("method", "")),
            str(finding.get("alert_name", "")),
        ]
    )


def _sca_fingerprint_key(tool_name: str, finding: dict[str, Any]) -> str:
    tool = finding.get("tool") or tool_name
    return "|".join(
        [
            str(tool),
            str(finding.get("package_name", "")),
            str(finding.get("vulnerability_id", "")),
            str(finding.get("ecosystem", "")),
        ]
    )


def _noir_fingerprint_key(finding: dict[str, Any]) -> str:
    return "|".join(
        [
            "noir",
            str(finding.get("method", "")),
            str(finding.get("url", "")),
        ]
    )


FINGERPRINT_REGISTRY: dict[str, Any] = {
    "gitleaks": _gitleaks_fingerprint_key,
    "semgrep": _semgrep_fingerprint_key,
    "zap": _zap_fingerprint_key,
    "noir": _noir_fingerprint_key,
    "pip-audit": lambda f: _sca_fingerprint_key("pip-audit", f),
    "npm-audit": lambda f: _sca_fingerprint_key("npm-audit", f),
    "composer-audit": lambda f: _sca_fingerprint_key("composer-audit", f),
    "osv-scanner": lambda f: _sca_fingerprint_key("osv-scanner", f),
}
