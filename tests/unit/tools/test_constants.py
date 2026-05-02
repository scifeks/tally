"""Tests for core/tools/constants.py. No external dependencies required."""

from domain.tools.constants import (
    BOOLEAN_TYPE_FIELDS,
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_LEVELS,
    DOMAINS,
    ENRICHMENT_FIELDS,
    FINDING_TYPES,
    SEVERITY_HIGH,
    SEVERITY_LEVELS,
    FieldSource,
)


def test_finding_types() -> None:
    assert FINDING_TYPES == {
        "secret",
        "vulnerability",
        "weakness",
        "misconfiguration",
        "exposure",
        "dependency",
        "informational",
    }


def test_severity_levels() -> None:
    assert SEVERITY_LEVELS == {"critical", "high", "medium", "low", "informational"}


def test_confidence_levels() -> None:
    assert CONFIDENCE_LEVELS == {"confirmed", "probable", "potential", "false_positive"}


def test_severity_high_constant() -> None:
    assert SEVERITY_HIGH == "high"


def test_confidence_confirmed_constant() -> None:
    assert CONFIDENCE_CONFIRMED == "confirmed"


def test_enrichment_fields_includes_confidence() -> None:
    assert "confidence" in ENRICHMENT_FIELDS


def test_domains() -> None:
    assert DOMAINS == {"code", "web"}


def test_field_source_attributes_exist() -> None:
    assert hasattr(FieldSource, "TOOL")
    assert hasattr(FieldSource, "ENRICHMENT")
    assert hasattr(FieldSource, "RULE")


def test_field_source_values_distinct() -> None:
    values = [FieldSource.TOOL, FieldSource.ENRICHMENT, FieldSource.RULE]
    assert len(set(values)) == 3


def test_boolean_type_fields() -> None:
    assert BOOLEAN_TYPE_FIELDS == {f"type_{t}" for t in FINDING_TYPES}


def test_enrichment_fields_valid_sources() -> None:
    valid = {FieldSource.TOOL, FieldSource.ENRICHMENT, FieldSource.RULE}
    for field, source in ENRICHMENT_FIELDS.items():
        assert source in valid, f"{field!r} has unknown source {source!r}"
