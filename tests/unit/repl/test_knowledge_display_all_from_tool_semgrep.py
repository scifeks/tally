"""Unit tests for _all_from_tool with semgrep results."""

from __future__ import annotations

from typing import Any

from application.repl.commands.findings_table import _all_from_tool


def _semgrep_result(
    rule_id: str = "php.lang.security.injection.taint.sink",
    file_path: str = "/src/BookingController.php",
    line_start: int = 42,
    severity: str = "medium",
    cwe: str = "",
    owasp: str = "",
    distance: float | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "tool": "semgrep",
        "domain": "code",
        "severity": severity,
        "rule_id": rule_id,
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_start + 2,
        "type_vulnerability": True,
        "type_weakness": True,
    }
    if cwe:
        meta["cwe"] = cwe
    if owasp:
        meta["owasp"] = owasp
    return {
        "document": (
            f"[semgrep] [{severity.upper()}] {rule_id} in {file_path}:{line_start}"
        ),
        "metadata": meta,
        "distance": distance,
    }


def _nmap_result(distance: float | None = None) -> dict[str, Any]:
    return {
        "document": "[nmap] Host 127.0.0.1 port 22 open ssh",
        "metadata": {
            "tool": "nmap",
            "domain": "network",
            "severity": "informational",
            "risk_type": "exposed_service",
            "type_exposure": True,
        },
        "distance": distance,
    }


class TestAllFromToolSemgrep:
    def test_all_semgrep_returns_true(self) -> None:
        results = [_semgrep_result(), _semgrep_result(rule_id="other.rule")]
        assert _all_from_tool(results, "semgrep") is True

    def test_mixed_semgrep_and_nmap_returns_false(self) -> None:
        results = [_semgrep_result(), _nmap_result()]
        assert _all_from_tool(results, "semgrep") is False

    def test_single_semgrep_returns_true(self) -> None:
        assert _all_from_tool([_semgrep_result()], "semgrep") is True
