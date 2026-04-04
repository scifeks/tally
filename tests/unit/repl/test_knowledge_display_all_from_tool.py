"""Unit tests for _all_from_tool."""

from __future__ import annotations

from typing import Any

from application.repl.commands.findings_table import _all_from_tool


def _gitleaks_result(
    file_path: str = "/src/app.py",
    line_number: int = 42,
    risk_type: str = "generic-api-key",
    severity: str = "high",
    distance: float | None = None,
) -> dict[str, Any]:
    return {
        "document": (
            f"[gitleaks] Secret detected: {risk_type} in {file_path}:{line_number}"
        ),
        "metadata": {
            "tool": "gitleaks",
            "domain": "code",
            "severity": severity,
            "risk_type": risk_type,
            "file_path": file_path,
            "line_number": line_number,
            "type_secret": True,
        },
        "distance": distance,
    }


def _semgrep_result(distance: float | None = None) -> dict[str, Any]:
    return {
        "document": "[semgrep] SQL injection in /src/db.py:10",
        "metadata": {
            "tool": "semgrep",
            "domain": "code",
            "severity": "high",
            "risk_type": "injection",
            "type_vulnerability": True,
        },
        "distance": distance,
    }


class TestAllFromTool:
    def test_empty_list_returns_false(self) -> None:
        assert _all_from_tool([], "gitleaks") is False

    def test_single_matching_result(self) -> None:
        assert _all_from_tool([_gitleaks_result()], "gitleaks") is True

    def test_multiple_matching_results(self) -> None:
        results = [_gitleaks_result(), _gitleaks_result(file_path="/other.py")]
        assert _all_from_tool(results, "gitleaks") is True

    def test_single_non_matching_result(self) -> None:
        assert _all_from_tool([_semgrep_result()], "gitleaks") is False

    def test_mixed_tools_returns_false(self) -> None:
        results = [_gitleaks_result(), _semgrep_result()]
        assert _all_from_tool(results, "gitleaks") is False

    def test_non_gitleaks_tool_name(self) -> None:
        assert _all_from_tool([_semgrep_result()], "semgrep") is True
