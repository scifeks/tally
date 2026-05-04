from application.pre_triage.scoring import (
    SqlInjectionClassifier,
    classify_score_band,
    classifier_score_to_dict,
)
from application.pre_triage.scorers.registry import default_classifier_registry


def make_dossier(
    *,
    rule_id: str = "php.lang.security.audit.sqli",
    description: str = "Possible SQL injection",
    relative_file: str = "vulnerabilities/sqli/source/low.php",
    absolute_file: str = "/test-php/vulnerabilities/sqli/source/low.php",
    confidence: str | None = "medium",
    meta: dict | None = None,
    reachable: bool = True,
    unresolved_callers: list[dict] | None = None,
    snippets: list[dict] | None = None,
) -> dict:
    return {
        "finding": {
            "id": 5,
            "rule_id": rule_id,
            "confidence": confidence,
            "description": description,
            "relative_file": relative_file,
            "absolute_file": absolute_file,
            "meta": meta
            or {
                "validation_state": "NO_VALIDATOR",
                "metadata": {
                    "confidence": "MEDIUM",
                    "vulnerability_class": ["SQL Injection"],
                    "source": "https://semgrep.dev/r/php.lang.security.injection.tainted-sql-string.tainted-sql-string",
                },
            },
        },
        "symbol_found": True,
        "reachability": {
            "reachable_from_entrypoint": reachable,
            "paths": [["index.php", "runQuery"]],
        },
        "graph": {
            "unresolved_callers": unresolved_callers or [],
        },
        "snippets": snippets
        or [
            {
                "kind": "finding_window",
                "features": ["reads_get", "uses_sql"],
                "code": "$id = $_GET['id'];\n$db->query(\"SELECT * FROM users WHERE id = $id\");",
            }
        ],
    }


def test_sqli_classifier_matches_sql_rule_id() -> None:
    classifier = SqlInjectionClassifier()

    assert classifier.matches_dossier(make_dossier())


def test_sqli_classifier_high_score_for_direct_source_sink_path() -> None:
    classifier = SqlInjectionClassifier()

    result = classifier.score_dossier(make_dossier())

    assert result.matched is True
    assert result.score >= 8.0
    assert classify_score_band(result.score) == "auto_escalate"
    assert any(item.name == "semgrep_metadata" for item in result.contributions)
    assert any(item.name == "validation_state" for item in result.contributions)


def test_sqli_classifier_penalizes_barriers_and_missing_reachability() -> None:
    classifier = SqlInjectionClassifier()
    dossier = make_dossier(
        reachable=False,
        snippets=[
            {
                "kind": "finding_window",
                "features": ["reads_get", "uses_sql"],
                "code": "$id = intval($_GET['id']);\n$stmt = $db->prepare('SELECT * FROM users WHERE id = ?');",
            }
        ],
    )

    result = classifier.score_dossier(dossier)

    assert result.score < 8.0
    assert classify_score_band(result.score) in {"priority_triage", "deprioritized"}
    assert any(item.name == "barrier_penalty" for item in result.contributions)


def test_sqli_classifier_returns_unmatched_score_for_non_sql_finding() -> None:
    classifier = SqlInjectionClassifier()
    dossier = make_dossier(
        rule_id="php.xss.reflected",
        description="Possible reflected XSS",
        relative_file="vulnerabilities/xss_r/source/low.php",
        absolute_file="/test-php/vulnerabilities/xss_r/source/low.php",
        snippets=[
            {
                "kind": "finding_window",
                "features": ["reads_get"],
                "code": "echo $_GET['q'];",
            }
        ],
        meta={
            "validation_state": "NO_VALIDATOR",
            "metadata": {
                "confidence": "HIGH",
                "vulnerability_class": ["Cross-Site Scripting"],
                "source": "https://semgrep.dev/r/php.xss.reflected",
            },
        },
    )

    result = classifier.score_dossier(dossier)

    assert result.matched is False
    assert result.score == 0.0
    assert classifier_score_to_dict(result)["score_band"] == "no_evidence"


def test_sqli_classifier_matches_semgrep_metadata_without_sqli_rule_id() -> None:
    classifier = SqlInjectionClassifier()
    dossier = make_dossier(
        rule_id="custom.php.rule",
        description="User data flows into a dangerous query builder",
    )

    result = classifier.score_dossier(dossier)

    assert result.matched is True
    assert any(item.name == "semgrep_metadata" for item in result.contributions)
    assert any("SQL Injection" in item for item in result.evidence)


def test_sqli_classifier_ignores_context_only_sql_for_non_sqli_finding() -> None:
    classifier = SqlInjectionClassifier()
    dossier = make_dossier(
        rule_id="php.lang.security.audit.exec-use",
        description="User data reaches exec",
        confidence="high",
        snippets=[
            {
                "kind": "finding_window",
                "features": ["reads_get"],
                "code": "system($_GET['cmd']);",
            },
            {
                "kind": "caller",
                "features": ["uses_sql"],
                "code": "$db->query(\"SELECT * FROM users\");",
            },
        ],
        meta={
            "validation_state": "NO_VALIDATOR",
            "metadata": {
                "confidence": "HIGH",
                "vulnerability_class": ["Command Injection"],
                "source": "https://semgrep.dev/r/php.lang.security.audit.exec-use",
            },
        },
    )

    result = classifier.score_dossier(dossier)

    assert result.matched is False
    assert result.score == 0.0


def test_sqli_classifier_reduces_score_when_semgrep_reports_validator() -> None:
    classifier = SqlInjectionClassifier()
    dossier = make_dossier(
        meta={
            "validation_state": "HAS_VALIDATOR",
            "metadata": {
                "confidence": "MEDIUM",
                "vulnerability_class": ["SQL Injection"],
                "source": "https://semgrep.dev/r/php.lang.security.injection.tainted-sql-string.tainted-sql-string",
            },
        },
    )

    result = classifier.score_dossier(dossier)

    assert any(item.name == "validation_state" for item in result.contributions)
    assert any("HAS_VALIDATOR" in item for item in result.assumptions)
    assert result.score < 10.0


def test_default_registry_returns_best_match_for_sql_dossier() -> None:
    registry = default_classifier_registry()

    result = registry.score_dossier(make_dossier())

    assert len(result["classifiers"]) == 1
    assert result["best_match"] is not None
    assert result["best_match"]["classifier_id"] == "php.sqli.v1"
