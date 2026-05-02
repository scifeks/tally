"""Field configuration for the SPA."""

from __future__ import annotations

from fastapi import APIRouter

from domain.findings.severity import Severity
from domain.tools.constants import (
    CONFIDENCE_LEVELS,
    DOMAINS,
    FINDING_TYPES,
    STATUS_LEVELS,
)

router = APIRouter()


@router.get("/field-specs")
def get_config() -> dict:
    """Return editable field specifications for the findings SPA.

    The response drives AG Grid column editability and cell editor params.
    The SPA reads allowed values from this endpoint at startup.
    Each field entry contains an editor type (select, text, boolean, tags)
    and optional allowed values. The enums section contains canonical
    allowed-value sets from domain constants.
    """
    return {
        "editable_fields": {
            "severity": {
                "editor": "select",
                "options": ["critical", "high", "medium", "low", "informational"],
            },
            "confidence": {
                "editor": "select",
                "options": sorted(CONFIDENCE_LEVELS),
            },
            "status": {
                "editor": "select",
                "options": sorted(STATUS_LEVELS),
            },
            "finding_type": {
                "editor": "tags",
                "options": sorted(FINDING_TYPES),
            },
            "description": {"editor": "text"},
            "business_impact": {"editor": "text"},
            "tal_id": {"editor": "text"},
            "cwe": {"editor": "tags"},
            "meta_title": {"editor": "text"},
            "meta_remediation": {"editor": "text"},
            "meta_risk_type": {"editor": "text"},
            "meta_owasp_name": {"editor": "text"},
            "meta_tags": {"editor": "tags"},
        },
        "enums": {
            "severities": [s.label for s in Severity.all_ordered()],
            "confidence_levels": sorted(CONFIDENCE_LEVELS),
            "statuses": sorted(STATUS_LEVELS),
            "finding_types": sorted(FINDING_TYPES),
            "domains": sorted(DOMAINS),
        },
    }
