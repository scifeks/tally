"""Dedicated prompt for the ``owasp_name`` enrichment field.

Provides a structured prompt that constrains the LLM to return an exact value
from the OWASP Top 10 Name column, or null if no confident match exists.
"""

from __future__ import annotations

from typing import Any

_OWASP_FIELD_DEFINITION = (
    "Field to populate: owasp_name\n"
    "  The OWASP Top 10 category Name that best describes this finding.\n"
    '  Return ONLY a value from the "Name" column of the tables below'
    " — copied exactly.\n"
    "  Return null if you cannot confidently map this finding to any category.\n"
    "  Do not guess. Do not invent values.\n"
    "\n"
    "  OWASP Top 10:2025\n"
    "  | Code       | Name                                    |\n"
    "  |------------|-----------------------------------------|\n"
    "  | A01:2025   | Broken Access Control                   |\n"
    "  | A02:2025   | Security Misconfiguration               |\n"
    "  | A03:2025   | Software Supply Chain Failures          |\n"
    "  | A04:2025   | Cryptographic Failures                  |\n"
    "  | A05:2025   | Injection                               |\n"
    "  | A06:2025   | Insecure Design                         |\n"
    "  | A07:2025   | Authentication Failures                 |\n"
    "  | A08:2025   | Software or Data Integrity Failures     |\n"
    "  | A09:2025   | Security Logging and Alerting Failures  |\n"
    "  | A10:2025   | Mishandling of Exceptional Conditions   |\n"
    "\n"
    "  OWASP Top 10:2021\n"
    "  | Code       | Name                                        |\n"
    "  |------------|---------------------------------------------|\n"
    "  | A01:2021   | Broken Access Control                       |\n"
    "  | A02:2021   | Cryptographic Failures                      |\n"
    "  | A03:2021   | Injection                                   |\n"
    "  | A04:2021   | Insecure Design                             |\n"
    "  | A05:2021   | Security Misconfiguration                   |\n"
    "  | A06:2021   | Vulnerable and Outdated Components          |\n"
    "  | A07:2021   | Identification and Authentication Failures  |\n"
    "  | A08:2021   | Software and Data Integrity Failures        |\n"
    "  | A09:2021   | Security Logging and Monitoring Failures    |\n"
    "  | A10:2021   | Server-Side Request Forgery (SSRF)          |\n"
    "\n"
    "  OWASP Top 10:2017\n"
    "  | Code      | Name                                          |\n"
    "  |-----------|-----------------------------------------------|\n"
    "  | A1:2017   | Injection                                     |\n"
    "  | A2:2017   | Broken Authentication                         |\n"
    "  | A3:2017   | Sensitive Data Exposure                       |\n"
    "  | A4:2017   | XML External Entities (XXE)                   |\n"
    "  | A5:2017   | Broken Access Control                         |\n"
    "  | A6:2017   | Security Misconfiguration                     |\n"
    "  | A7:2017   | Cross-Site Scripting (XSS)                    |\n"
    "  | A8:2017   | Insecure Deserialization                      |\n"
    "  | A9:2017   | Using Components with Known Vulnerabilities   |\n"
    "  | A10:2017  | Insufficient Logging and Monitoring           |\n"
)

_OWASP_PROMPT_TEMPLATE = (
    "Classify this security finding. Return only a JSON object with a single"
    ' field: "owasp_name". Do not include any other fields.'
    " No prose, no explanation, no markdown.\n"
    "\n"
    "Finding context:\n"
    "{context}\n"
    "\n"
    "{owasp_definition}"
    "\n"
    'Return: {{"owasp_name": "<exact Name value or null>"}}'
)


def render_prompt(source_values: dict[str, Any]) -> str:
    """Build the owasp_name prompt from extracted finding metadata values.

    Args:
        source_values: Dict of metadata key/value pairs already extracted
            from the finding (e.g. ``{"alert_name": "SQL Injection", ...}``).
            Missing source fields are silently omitted by the caller.

    Returns:
        Complete user-turn prompt string ready for the LLM.
    """
    context = "\n".join(f"{k}: {v}" for k, v in source_values.items())
    return _OWASP_PROMPT_TEMPLATE.format(
        context=context,
        owasp_definition=_OWASP_FIELD_DEFINITION,
    )
