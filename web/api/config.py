"""GET /api/v1/config/field-specs — field configuration for the SPA."""

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
    The SPA must not hardcode allowed values for any field — it reads them
    here at startup.

    Each entry in ``editable_fields`` describes one patchable field:
    - ``editor``: ``"select"`` | ``"text"`` | ``"boolean"`` | ``"tags"``
    - ``options``: present only for ``"select"`` and ``"tags"`` editors;
      lists the allowed values in display order.
    ``enums`` contains the canonical allowed-value sets sourced from
    ``domain.tools.constants`` and ``domain.findings.severity``.
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
