"""Tests for core/tools/constants.py — no external dependencies required."""

from core.tools.constants import (
    BOOLEAN_TYPE_FIELDS,
    DOMAINS,
    ENRICHMENT_FIELDS,
    FINDING_TYPES,
    SEVERITY_LEVELS,
    TOOL_DOMAIN_MAP,
    TOOL_PROVIDED_FIELDS,
    TOOL_TYPE_MAP,
    FieldSource,
)

INGESTOR_TOOLS: set[str] = {
    "nmap",
    "semgrep",
    "osv-scanner",
    "pip-audit",
    "npm-audit",
    "composer-audit",
    "gitleaks",
    "zap",
}


def test_finding_types() -> None:
    assert FINDING_TYPES == {
        "secret",
        "vulnerability",
        "weakness",
        "misconfiguration",
        "exposure",
        "dependency",
    }


def test_severity_levels() -> None:
    assert SEVERITY_LEVELS == {"confirmed", "probable", "potential", "informational"}


def test_domains() -> None:
    assert DOMAINS == {"code", "web", "network"}


def test_field_source_attributes_exist() -> None:
    assert hasattr(FieldSource, "TOOL")
    assert hasattr(FieldSource, "ENRICHMENT")
    assert hasattr(FieldSource, "RULE")


def test_field_source_values_distinct() -> None:
    values = [FieldSource.TOOL, FieldSource.ENRICHMENT, FieldSource.RULE]
    assert len(set(values)) == 3


def test_tool_domain_map_keys() -> None:
    assert set(TOOL_DOMAIN_MAP.keys()) == INGESTOR_TOOLS


def test_tool_type_map_keys() -> None:
    assert set(TOOL_TYPE_MAP.keys()) == INGESTOR_TOOLS


def test_tool_provided_fields_keys() -> None:
    assert set(TOOL_PROVIDED_FIELDS.keys()) == INGESTOR_TOOLS


def test_tool_domain_map_values_in_domains() -> None:
    for tool, domain in TOOL_DOMAIN_MAP.items():
        assert domain in DOMAINS, f"{tool!r} maps to unknown domain {domain!r}"


def test_boolean_type_fields() -> None:
    assert BOOLEAN_TYPE_FIELDS == {f"type_{t}" for t in FINDING_TYPES}


def test_enrichment_fields_valid_sources() -> None:
    valid = {FieldSource.TOOL, FieldSource.ENRICHMENT, FieldSource.RULE}
    for field, source in ENRICHMENT_FIELDS.items():
        assert source in valid, f"{field!r} has unknown source {source!r}"
