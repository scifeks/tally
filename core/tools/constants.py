SCAN_SEGMENTS: dict[str, list[str]] = {
    "network": ["nmap"],
    "sast": ["semgrep"],
    "sca": ["osv-scanner", "pip-audit", "npm-audit", "composer-audit"],
    "secrets": ["gitleaks"],
    "api": ["zap"],
}


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
}

SEVERITY_LEVELS: set[str] = {
    "confirmed",
    "probable",
    "potential",
    "informational",
}

SEVERITY_INFORMATIONAL = "informational"

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

TOOL_TYPE_MAP: dict[str, str] = {
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
    "gitleaks": {"severity", "risk_type"},
    "semgrep": {"severity"},
    "zap": {"severity", "remediation", "description"},
    "nmap": {"severity", "risk_type", "remediation", "description"},
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
    "description": FieldSource.ENRICHMENT,
}
