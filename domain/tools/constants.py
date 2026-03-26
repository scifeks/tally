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

STATUS_LEVELS: frozenset[str] = frozenset(
    {"active", "false_positive", "fixed", "wont_fix"}
)

DOMAINS: set[str] = {"code", "web", "network"}

BOOLEAN_TYPE_FIELDS: set[str] = {f"type_{t}" for t in FINDING_TYPES}

ENRICHMENT_FIELDS: dict[str, str] = {
    "risk_type": FieldSource.ENRICHMENT,
    "remediation": FieldSource.ENRICHMENT,
    "severity": FieldSource.ENRICHMENT,
    "confidence": FieldSource.ENRICHMENT,
    "description": FieldSource.ENRICHMENT,
    "owasp_name": FieldSource.ENRICHMENT,
    "title": FieldSource.ENRICHMENT,
}

OWASP_CODE_TO_NAME: dict[str, str] = {
    # OWASP Top 10:2025
    "A01:2025": "Broken Access Control",
    "A02:2025": "Security Misconfiguration",
    "A03:2025": "Software Supply Chain Failures",
    "A04:2025": "Cryptographic Failures",
    "A05:2025": "Injection",
    "A06:2025": "Insecure Design",
    "A07:2025": "Authentication Failures",
    "A08:2025": "Software or Data Integrity Failures",
    "A09:2025": "Security Logging and Alerting Failures",
    "A10:2025": "Mishandling of Exceptional Conditions",
    # OWASP Top 10:2021
    "A01:2021": "Broken Access Control",
    "A02:2021": "Cryptographic Failures",
    "A03:2021": "Injection",
    "A04:2021": "Insecure Design",
    "A05:2021": "Security Misconfiguration",
    "A06:2021": "Vulnerable and Outdated Components",
    "A07:2021": "Identification and Authentication Failures",
    "A08:2021": "Software and Data Integrity Failures",
    "A09:2021": "Security Logging and Monitoring Failures",
    "A10:2021": "Server-Side Request Forgery (SSRF)",
    # OWASP Top 10:2017
    "A1:2017": "Injection",
    "A2:2017": "Broken Authentication",
    "A3:2017": "Sensitive Data Exposure",
    "A4:2017": "XML External Entities (XXE)",
    "A5:2017": "Broken Access Control",
    "A6:2017": "Security Misconfiguration",
    "A7:2017": "Cross-Site Scripting (XSS)",
    "A8:2017": "Insecure Deserialization",
    "A9:2017": "Using Components with Known Vulnerabilities",
    "A10:2017": "Insufficient Logging and Monitoring",
}

OWASP_NAMES: frozenset[str] = frozenset(OWASP_CODE_TO_NAME.values())
