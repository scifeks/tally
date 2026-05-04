import json

from application.pre_triage.semgrep_artifact import (
    load_semgrep_findings,
    normalize_absolute_file,
    normalize_relative_file,
)


def test_normalize_relative_file_strips_local_target_root() -> None:
    result = normalize_relative_file(
        "application/pre_triage/test-php/vulnerabilities/sqli/source/low.php",
        local_target_root="application/pre_triage/test-php",
    )

    assert result == "/vulnerabilities/sqli/source/low.php"


def test_normalize_absolute_file_uses_analyzer_root() -> None:
    result = normalize_absolute_file(
        "/vulnerabilities/sqli/source/low.php",
        target_root="/test-php",
    )

    assert result == "/test-php/vulnerabilities/sqli/source/low.php"


def test_load_semgrep_findings_filters_by_rule_id(tmp_path) -> None:
    artifact = tmp_path / "semgrep.json"
    artifact.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "check_id": "php.lang.security.injection.tainted-sql-string.tainted-sql-string",
                        "path": "application/pre_triage/test-php/vulnerabilities/sqli/source/low.php",
                        "start": {"line": 10},
                        "end": {"line": 10},
                        "extra": {
                            "message": "SQLi",
                            "severity": "ERROR",
                            "metadata": {"confidence": "MEDIUM"},
                            "engine_kind": "OSS",
                            "validation_state": "NO_VALIDATOR",
                        },
                    },
                    {
                        "check_id": "php.lang.security.exec-use.exec-use",
                        "path": "application/pre_triage/test-php/vulnerabilities/exec/source/low.php",
                        "start": {"line": 12},
                        "end": {"line": 12},
                        "extra": {
                            "message": "Exec",
                            "severity": "WARNING",
                            "metadata": {"confidence": "LOW"},
                            "engine_kind": "OSS",
                            "validation_state": "NO_VALIDATOR",
                        },
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    findings = load_semgrep_findings(
        artifact,
        target_root="/test-php",
        local_target_root="application/pre_triage/test-php",
        rule_id="php.lang.security.injection.tainted-sql-string.tainted-sql-string",
    )

    assert len(findings) == 1
    assert findings[0].rule_id == "php.lang.security.injection.tainted-sql-string.tainted-sql-string"
    assert findings[0].relative_file == "/vulnerabilities/sqli/source/low.php"
    assert findings[0].absolute_file == "/test-php/vulnerabilities/sqli/source/low.php"
    assert findings[0].confidence == "medium"
