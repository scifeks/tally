class FieldSource:
    TOOL = "tool"
    ENRICHMENT = "enrichment"
    RULE = "rule"


FINDING_TYPES: set[str] = {
    "secret",
    "vulnerability",
    "weakness",
    "misconfiguration",
    "exposure",
    "dependency",
    "informational",
}

SEVERITY_LEVELS: set[str] = {
    "critical",
    "high",
    "medium",
    "low",
    "informational",
}

CONFIDENCE_LEVELS: set[str] = {
    "confirmed",
    "probable",
    "potential",
    "false_positive",
}

SEVERITY_INFORMATIONAL = "informational"
SEVERITY_HIGH = "high"
CONFIDENCE_CONFIRMED = "confirmed"

DOMAINS: set[str] = {"structure", "code", "web", "network"}

BOOLEAN_TYPE_FIELDS: set[str] = {f"type_{t}" for t in FINDING_TYPES}

ENRICHMENT_FIELDS: dict[str, str] = {
    "risk_type": FieldSource.ENRICHMENT,
    "remediation": FieldSource.ENRICHMENT,
    "severity": FieldSource.ENRICHMENT,
    "confidence": FieldSource.ENRICHMENT,
    "description": FieldSource.ENRICHMENT,
}
