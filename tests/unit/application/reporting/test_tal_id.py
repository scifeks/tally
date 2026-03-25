"""Unit tests for application.reporting.tal_id."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.tal_id import assign_tal_ids, resolve_prefix  # noqa: E402


class TestAssignTalIds:
    def test_empty_input_returns_empty_list(self) -> None:
        assert assign_tal_ids([]) == []

    def test_single_finding_gets_tal_001(self) -> None:
        result = assign_tal_ids([{"severity": "high"}], prefix="TAL")
        assert result[0]["tal_id"] == "TAL-001"

    def test_sequential_assignment(self) -> None:
        findings = [{"severity": "high"}, {"severity": "medium"}, {"severity": "low"}]
        result = assign_tal_ids(findings, prefix="TAL")
        assert [r["tal_id"] for r in result] == ["TAL-001", "TAL-002", "TAL-003"]

    def test_no_prefix_numeric_only(self) -> None:
        result = assign_tal_ids([{"severity": "high"}])
        assert result[0]["tal_id"] == "001"

    def test_custom_prefix(self) -> None:
        result = assign_tal_ids([{"severity": "high"}], prefix="FOO")
        assert result[0]["tal_id"] == "FOO-001"

    def test_original_dicts_not_mutated(self) -> None:
        findings = [{"severity": "critical"}]
        assign_tal_ids(findings, prefix="TAL")
        assert "tal_id" not in findings[0]

    def test_zero_padding_at_999(self) -> None:
        findings = [{"severity": "low"}] * 999
        result = assign_tal_ids(findings, prefix="TAL")
        assert result[0]["tal_id"] == "TAL-001"
        assert result[998]["tal_id"] == "TAL-999"

    def test_auto_expands_to_4_digits_at_1000(self) -> None:
        findings = [{"severity": "low"}] * 1000
        result = assign_tal_ids(findings, prefix="TAL")
        assert result[0]["tal_id"] == "TAL-0001"
        assert result[999]["tal_id"] == "TAL-1000"

    def test_auto_expands_to_4_digits_at_1001(self) -> None:
        findings = [{"severity": "low"}] * 1001
        result = assign_tal_ids(findings, prefix="TAL")
        assert result[0]["tal_id"] == "TAL-0001"
        assert result[1000]["tal_id"] == "TAL-1001"

    def test_existing_fields_preserved(self) -> None:
        findings = [{"severity": "high", "rule_id": "sqli-001"}]
        result = assign_tal_ids(findings, prefix="TAL")
        assert result[0]["rule_id"] == "sqli-001"
        assert result[0]["severity"] == "high"

    def test_order_preserved(self) -> None:
        findings = [
            {"severity": "critical", "first_seen": "2024-01-01"},
            {"severity": "high", "first_seen": "2024-01-02"},
            {"severity": "medium", "first_seen": "2024-01-03"},
            {"severity": "low", "first_seen": "2024-01-04"},
            {"severity": "informational", "first_seen": "2024-01-05"},
        ]
        result = assign_tal_ids(findings, prefix="TAL")
        assert result[0]["tal_id"] == "TAL-001"
        assert result[0]["severity"] == "critical"
        assert result[4]["tal_id"] == "TAL-005"
        assert result[4]["severity"] == "informational"


class TestResolvePrefix:
    def test_abbreviation_takes_priority(self) -> None:
        assert resolve_prefix("FOO", "TAL") == "FOO"

    def test_global_used_when_no_abbreviation(self) -> None:
        assert resolve_prefix("", "TAL") == "TAL"

    def test_empty_both_returns_empty(self) -> None:
        assert resolve_prefix("", "") == ""

    def test_whitespace_stripped(self) -> None:
        assert resolve_prefix("  ", "TAL") == "TAL"
        assert resolve_prefix("FOO", "  ") == "FOO"
