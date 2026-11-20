"""Explicit registry of vulnerability-scanner skills Tally exposes to users.

Only vuln scanner skills belong here. Orchestration skills (tally-scan-external),
subagent definitions (tally-scan-domain, tally-scan-recon), and the adversarial
verification skill are not user-filterable and are intentionally omitted.
"""

from __future__ import annotations

from dataclasses import dataclass


class UnknownScannerSkill(Exception):
    pass


@dataclass(frozen=True)
class ScannerEntry:
    full_slug: str
    display_slug: str
    family: str
    description: str


_REGISTRY: tuple[tuple[str, str, str], ...] = (
    # (full_slug, family, description)
    ("tally-scan-injection-sql", "injection", "SQL injection detection."),
    ("tally-scan-injection-nosql", "injection", "NoSQL injection detection."),
    ("tally-scan-injection-os-command", "injection", "OS command injection detection."),
    (
        "tally-scan-injection-template",
        "injection",
        "Server-side template injection detection.",
    ),
    ("tally-scan-injection-ldap", "injection", "LDAP injection detection."),
    ("tally-scan-injection-xpath", "injection", "XPath injection detection."),
    (
        "tally-scan-injection-eval",
        "injection",
        "Eval and dynamic code execution detection.",
    ),
    ("tally-scan-injection-header", "injection", "HTTP header injection detection."),
    (
        "tally-scan-injection-reflection",
        "injection",
        "Reflection and metaprogramming injection detection.",
    ),
    (
        "tally-scan-injection-prototype-pollution",
        "injection",
        "Prototype pollution detection.",
    ),
    ("tally-scan-xss-stored", "xss", "Stored XSS detection."),
    ("tally-scan-xss-reflected", "xss", "Reflected XSS detection."),
    ("tally-scan-xss-blind", "xss", "Blind XSS detection."),
    ("tally-scan-access-control-csrf", "access-control", "CSRF detection."),
    ("tally-scan-access-control-idor-bola", "access-control", "IDOR / BOLA detection."),
    (
        "tally-scan-access-control-incorrect-authz-logic",
        "access-control",
        "Incorrect authorization logic detection.",
    ),
    (
        "tally-scan-access-control-mass-assignment",
        "access-control",
        "Mass assignment detection.",
    ),
    (
        "tally-scan-access-control-missing-function-authz",
        "access-control",
        "Missing function-level authorization detection.",
    ),
    (
        "tally-scan-access-control-open-redirect",
        "access-control",
        "Open redirect detection.",
    ),
    (
        "tally-scan-access-control-path-traversal",
        "access-control",
        "Path traversal detection.",
    ),
    (
        "tally-scan-authentication-session-management",
        "authentication",
        "Session management flaws.",
    ),
    (
        "tally-scan-authentication-weak-or-missing-authn",
        "authentication",
        "Weak or missing authentication.",
    ),
    ("tally-scan-crypto-hardcoded-secrets", "crypto", "Hard-coded secrets detection."),
    ("tally-scan-crypto-pii-in-logs", "crypto", "PII in logs."),
    ("tally-scan-crypto-pii-in-response", "crypto", "PII leaked in responses."),
    ("tally-scan-crypto-weak-algorithm", "crypto", "Weak cryptographic algorithms."),
    ("tally-scan-crypto-weak-password-hashing", "crypto", "Weak password hashing."),
    ("tally-scan-crypto-weak-prng", "crypto", "Weak PRNG usage."),
    (
        "tally-scan-data-integrity-file-upload",
        "data-integrity",
        "Unsafe file upload handling.",
    ),
    (
        "tally-scan-data-integrity-insecure-deserialization",
        "data-integrity",
        "Insecure deserialization.",
    ),
    (
        "tally-scan-data-integrity-missing-integrity-verification",
        "data-integrity",
        "Missing integrity verification.",
    ),
    (
        "tally-scan-design-logic-insufficient-logging",
        "design-logic",
        "Insufficient logging.",
    ),
    (
        "tally-scan-design-logic-missing-exception-handling",
        "design-logic",
        "Missing exception handling.",
    ),
    (
        "tally-scan-design-logic-order-of-operations",
        "design-logic",
        "Order-of-operations defects.",
    ),
    ("tally-scan-design-logic-race-condition", "design-logic", "Race conditions."),
    (
        "tally-scan-design-logic-toctou",
        "design-logic",
        "Time-of-check / time-of-use flaws.",
    ),
    ("tally-scan-misconfig-cors", "misconfig", "CORS misconfiguration."),
    ("tally-scan-misconfig-csp", "misconfig", "CSP misconfiguration."),
    (
        "tally-scan-misconfig-error-message-exposure",
        "misconfig",
        "Error-message information disclosure.",
    ),
    (
        "tally-scan-misconfig-framework-defaults",
        "misconfig",
        "Insecure framework defaults.",
    ),
    (
        "tally-scan-misconfig-insecure-file-permissions",
        "misconfig",
        "Insecure file permissions.",
    ),
    (
        "tally-scan-misconfig-security-headers",
        "misconfig",
        "Missing or weak security headers.",
    ),
    ("tally-scan-misconfig-jwt-alg-confusion", "jwt", "JWT algorithm confusion."),
    ("tally-scan-misconfig-jwt-jwks-injection", "jwt", "JWKS injection."),
    (
        "tally-scan-misconfig-jwt-missing-sig-verify",
        "jwt",
        "Missing JWT signature verification.",
    ),
    ("tally-scan-ssrf", "network", "Server-side request forgery."),
    ("tally-scan-xxe", "network", "XXE / XML external entity."),
)


def _build_entry(full_slug: str, family: str, description: str) -> ScannerEntry:
    if not full_slug.startswith("tally-"):
        raise ValueError(f"Registry entry {full_slug!r} must start with 'tally-'.")
    return ScannerEntry(
        full_slug=full_slug,
        display_slug=full_slug.removeprefix("tally-"),
        family=family,
        description=description,
    )


_ENTRIES: tuple[ScannerEntry, ...] = tuple(
    _build_entry(slug, family, desc) for slug, family, desc in _REGISTRY
)
_BY_DISPLAY = {e.display_slug: e for e in _ENTRIES}
_BY_FULL = {e.full_slug: e for e in _ENTRIES}


def list_scanners() -> list[ScannerEntry]:
    return list(_ENTRIES)


def resolve_display_slug(display: str) -> str:
    entry = _BY_DISPLAY.get(display)
    if entry is None:
        raise UnknownScannerSkill(
            f"No scanner skill registered for display slug {display!r}."
        )
    return entry.full_slug


def resolve_full_slug(full: str) -> str:
    entry = _BY_FULL.get(full)
    if entry is None:
        raise UnknownScannerSkill(
            f"No scanner skill registered for full slug {full!r}."
        )
    return entry.display_slug


def group_by_family() -> dict[str, list[ScannerEntry]]:
    out: dict[str, list[ScannerEntry]] = {}
    for entry in _ENTRIES:
        out.setdefault(entry.family, []).append(entry)
    return out
