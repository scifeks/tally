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
}

SEVERITY_INFORMATIONAL = "informational"
SEVERITY_HIGH = "high"
CONFIDENCE_CONFIRMED = "confirmed"

DOMAINS: set[str] = {"code", "web", "network"}

TOOL_DOMAIN_MAP: dict[str, str] = {
    "gitleaks": "code",
    "semgrep": "code",
    "pip-audit": "code",
    "npm-audit": "code",
    "osv-scanner": "code",
    "composer-audit": "code",
    "zap": "web",
    "nmap": "network",
}


TOOL_PROVIDED_FIELDS: dict[str, set[str]] = {
    "gitleaks": {"severity", "risk_type", "confidence"},
    "semgrep": {"severity"},
    "zap": {"severity", "confidence", "remediation", "description"},
    "nmap": {"severity", "confidence", "risk_type", "remediation", "description"},
    "pip-audit": {"severity"},
    "npm-audit": {"severity"},
    "osv-scanner": {"severity"},
    "composer-audit": set(),
}

BOOLEAN_TYPE_FIELDS: set[str] = {f"type_{t}" for t in FINDING_TYPES}

ENRICHMENT_FIELDS: dict[str, str] = {
    "risk_type": FieldSource.ENRICHMENT,
    "remediation": FieldSource.ENRICHMENT,
    "severity": FieldSource.ENRICHMENT,
    "confidence": FieldSource.ENRICHMENT,
    "description": FieldSource.ENRICHMENT,
}
