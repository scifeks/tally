"""Unit tests for the MCP finding payload validator."""

from __future__ import annotations

from typing import Any

import pytest

from application.mcp.finding_payload import (
    FindingPayloadError,
    validate_finding_payload,
)


def _valid_payload() -> dict[str, Any]:
    """Return a valid baseline finding payload."""
    return {
        "file": "src/db.py",
        "line_number": 42,
        "description": "SQL query built from user input via string concat.",
        "severity": "critical",
        "confidence": "confirmed",
        "cwe": ["CWE-89"],
        "finding_type": ["vulnerability"],
        "rule_id": "injection.sql",
        "meta": {
            "title": "SQL Injection in User Lookup",
            "owasp_name": "Injection",
            "remediation": "Use parameterized queries with sqlite3.",
        },
    }


class TestValidateFindingPayload:
    """Tests for finding payload validation."""

    def test_happy_path_returns_canonical(self) -> None:
        """Valid payload is returned normalized."""
        result = validate_finding_payload(_valid_payload())
        assert result["file"] == "src/db.py"
        assert result["line_number"] == 42

    def test_file_path_alias(self) -> None:
        """file_path alias is renamed to file in result."""
        payload = _valid_payload()
        payload.pop("file")
        payload["file_path"] = "src/db.py"
        result = validate_finding_payload(payload)
        assert result["file"] == "src/db.py"
        assert "file_path" not in result

    def test_line_start_alias(self) -> None:
        """line_start alias is renamed to line_number in result."""
        payload = _valid_payload()
        payload.pop("line_number")
        payload["line_start"] = 42
        result = validate_finding_payload(payload)
        assert result["line_number"] == 42
        assert "line_start" not in result

    def test_missing_file_raises(self) -> None:
        """Missing file and file_path raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("file")
        with pytest.raises(FindingPayloadError, match="file"):
            validate_finding_payload(payload)

    def test_missing_line_number_raises(self) -> None:
        """Missing line_number and line_start raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("line_number")
        with pytest.raises(FindingPayloadError, match="line"):
            validate_finding_payload(payload)

    def test_missing_description_raises(self) -> None:
        """Missing description raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("description")
        with pytest.raises(FindingPayloadError, match="description"):
            validate_finding_payload(payload)

    def test_missing_severity_raises(self) -> None:
        """Missing severity raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("severity")
        with pytest.raises(FindingPayloadError, match="severity"):
            validate_finding_payload(payload)

    def test_missing_confidence_raises(self) -> None:
        """Missing confidence raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("confidence")
        with pytest.raises(FindingPayloadError, match="confidence"):
            validate_finding_payload(payload)

    def test_missing_cwe_raises(self) -> None:
        """Missing cwe raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("cwe")
        with pytest.raises(FindingPayloadError, match="cwe"):
            validate_finding_payload(payload)

    def test_missing_finding_type_raises(self) -> None:
        """Missing finding_type raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("finding_type")
        with pytest.raises(FindingPayloadError, match="finding_type"):
            validate_finding_payload(payload)

    def test_missing_rule_id_raises(self) -> None:
        """Missing rule_id raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("rule_id")
        with pytest.raises(FindingPayloadError, match="rule_id"):
            validate_finding_payload(payload)

    def test_missing_meta_raises(self) -> None:
        """Missing meta raises FindingPayloadError."""
        payload = _valid_payload()
        payload.pop("meta")
        with pytest.raises(FindingPayloadError, match="meta"):
            validate_finding_payload(payload)

    def test_missing_meta_title_raises(self) -> None:
        """Missing meta.title raises FindingPayloadError."""
        payload = _valid_payload()
        del payload["meta"]["title"]
        with pytest.raises(FindingPayloadError, match="title"):
            validate_finding_payload(payload)

    def test_missing_meta_owasp_name_raises(self) -> None:
        """Missing meta.owasp_name raises FindingPayloadError."""
        payload = _valid_payload()
        del payload["meta"]["owasp_name"]
        with pytest.raises(FindingPayloadError, match="owasp_name"):
            validate_finding_payload(payload)

    def test_missing_meta_remediation_raises(self) -> None:
        """Missing meta.remediation raises FindingPayloadError."""
        payload = _valid_payload()
        del payload["meta"]["remediation"]
        with pytest.raises(FindingPayloadError, match="remediation"):
            validate_finding_payload(payload)

    def test_invalid_severity_raises(self) -> None:
        """Invalid severity value raises FindingPayloadError."""
        payload = _valid_payload()
        payload["severity"] = "totally_broken"
        with pytest.raises(FindingPayloadError, match="severity"):
            validate_finding_payload(payload)

    def test_invalid_confidence_raises(self) -> None:
        """Invalid confidence value raises FindingPayloadError."""
        payload = _valid_payload()
        payload["confidence"] = "totally_broken"
        with pytest.raises(FindingPayloadError, match="confidence"):
            validate_finding_payload(payload)

    def test_invalid_segment_raises(self) -> None:
        """Invalid segment value raises FindingPayloadError."""
        payload = _valid_payload()
        payload["segment"] = "totally_broken"
        with pytest.raises(FindingPayloadError, match="segment"):
            validate_finding_payload(payload)

    def test_empty_cwe_raises(self) -> None:
        """Empty cwe list raises FindingPayloadError."""
        payload = _valid_payload()
        payload["cwe"] = []
        with pytest.raises(FindingPayloadError, match="cwe"):
            validate_finding_payload(payload)

    def test_empty_finding_type_raises(self) -> None:
        """Empty finding_type list raises FindingPayloadError."""
        payload = _valid_payload()
        payload["finding_type"] = []
        with pytest.raises(FindingPayloadError, match="finding_type"):
            validate_finding_payload(payload)

    def test_unknown_top_level_key_raises(self) -> None:
        """Unknown top-level key raises FindingPayloadError."""
        payload = _valid_payload()
        payload["nonsense"] = "value"
        with pytest.raises(FindingPayloadError, match="nonsense"):
            validate_finding_payload(payload)

    def test_unknown_meta_key_passes(self) -> None:
        """Unknown meta key is preserved in output."""
        payload = _valid_payload()
        payload["meta"]["custom_key"] = "some analysis note"
        result = validate_finding_payload(payload)
        assert result["meta"]["custom_key"] == "some analysis note"

    def test_optional_segment_valid(self) -> None:
        """Valid optional segment is accepted."""
        payload = _valid_payload()
        payload["segment"] = "sast"
        result = validate_finding_payload(payload)
        assert result["segment"] == "sast"

    def test_optional_line_end(self) -> None:
        """Optional line_end is preserved."""
        payload = _valid_payload()
        payload["line_end"] = 45
        result = validate_finding_payload(payload)
        assert result["line_end"] == 45

    def test_optional_reasoning(self) -> None:
        """Optional reasoning is preserved."""
        payload = _valid_payload()
        payload["reasoning"] = "Pattern matches SQL injection vector."
        result = validate_finding_payload(payload)
        assert result["reasoning"] == "Pattern matches SQL injection vector."

    def test_optional_attack_vector(self) -> None:
        """Optional attack_vector is preserved."""
        payload = _valid_payload()
        payload["attack_vector"] = "Network"
        result = validate_finding_payload(payload)
        assert result["attack_vector"] == "Network"

    def test_optional_code_snippet(self) -> None:
        """Optional code_snippet is preserved."""
        payload = _valid_payload()
        payload["code_snippet"] = 'query = "SELECT * FROM users WHERE id=" + user_id'
        result = validate_finding_payload(payload)
        assert result["code_snippet"] == (
            'query = "SELECT * FROM users WHERE id=" + user_id'
        )

    def test_empty_description_raises(self) -> None:
        """Empty description raises FindingPayloadError."""
        payload = _valid_payload()
        payload["description"] = ""
        with pytest.raises(FindingPayloadError, match="description"):
            validate_finding_payload(payload)

    def test_empty_rule_id_raises(self) -> None:
        """Empty rule_id raises FindingPayloadError."""
        payload = _valid_payload()
        payload["rule_id"] = ""
        with pytest.raises(FindingPayloadError, match="rule_id"):
            validate_finding_payload(payload)

    def test_empty_meta_title_raises(self) -> None:
        """Empty meta.title raises FindingPayloadError."""
        payload = _valid_payload()
        payload["meta"]["title"] = ""
        with pytest.raises(FindingPayloadError, match="title"):
            validate_finding_payload(payload)

    def test_empty_meta_owasp_name_raises(self) -> None:
        """Empty meta.owasp_name raises FindingPayloadError."""
        payload = _valid_payload()
        payload["meta"]["owasp_name"] = ""
        with pytest.raises(FindingPayloadError, match="owasp_name"):
            validate_finding_payload(payload)

    def test_empty_meta_remediation_raises(self) -> None:
        """Empty meta.remediation raises FindingPayloadError."""
        payload = _valid_payload()
        payload["meta"]["remediation"] = ""
        with pytest.raises(FindingPayloadError, match="remediation"):
            validate_finding_payload(payload)

    def test_both_file_and_file_path_file_wins(self) -> None:
        """When both file and file_path present, file takes precedence."""
        payload = _valid_payload()
        payload["file"] = "src/db.py"
        payload["file_path"] = "src/other.py"
        result = validate_finding_payload(payload)
        assert result["file"] == "src/db.py"

    def test_both_line_number_and_line_start_number_wins(self) -> None:
        """When both line_number and line_start present, line_number wins."""
        payload = _valid_payload()
        payload["line_number"] = 42
        payload["line_start"] = 50
        result = validate_finding_payload(payload)
        assert result["line_number"] == 42

    def test_invalid_cwe_format_raises(self) -> None:
        """CWE entry not matching CWE-N pattern raises error."""
        payload = _valid_payload()
        payload["cwe"] = ["garbage"]
        with pytest.raises(FindingPayloadError, match="cwe"):
            validate_finding_payload(payload)

    def test_cwe_non_string_raises(self) -> None:
        """Non-string CWE entry raises error."""
        payload = _valid_payload()
        payload["cwe"] = [89]
        with pytest.raises(FindingPayloadError, match="cwe"):
            validate_finding_payload(payload)

    def test_valid_cwe_format_accepted(self) -> None:
        """CWE entries matching CWE-N pattern pass."""
        payload = _valid_payload()
        payload["cwe"] = ["CWE-89", "CWE-564"]
        result = validate_finding_payload(payload)
        assert result["cwe"] == ["CWE-89", "CWE-564"]

    def test_invalid_finding_type_raises(self) -> None:
        """finding_type not in allowed set raises error."""
        payload = _valid_payload()
        payload["finding_type"] = ["nonexistent"]
        with pytest.raises(FindingPayloadError, match="finding_type"):
            validate_finding_payload(payload)

    def test_valid_finding_types_accepted(self) -> None:
        """Known finding_type values pass."""
        payload = _valid_payload()
        payload["finding_type"] = ["vulnerability", "misconfiguration"]
        result = validate_finding_payload(payload)
        assert result["finding_type"] == [
            "vulnerability",
            "misconfiguration",
        ]
