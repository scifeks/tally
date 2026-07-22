"""Finding normalization and field routing."""

from __future__ import annotations

import json
import logging
from typing import Any, NamedTuple

from domain.findings.severity import Severity
from domain.tools.constants import FINDING_TYPES

logger = logging.getLogger(__name__)

# "severity" excluded: stored as integer rank, not a direct pass-through.
DIRECT_COLUMNS: tuple[str, ...] = (
    "tool",
    "domain",
    "segment",
    "confidence",
    "rule_id",
    "url",
    "vulnerability_id",
    "package_name",
    "ecosystem",
    "description",
    "package_version",
)

COMMA_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "technology",
        "subcategory",
        "references",
        "aliases",
        "tags",
    }
)

ANALYST_META_KEYS: frozenset[str] = frozenset(
    {
        "remediation",
        "risk_type",
        "owasp_name",
        "title",
        "tags",
        "notes",
    }
)

ENRICHMENT_META_FIELDS: frozenset[str] = frozenset(
    {"risk_type", "remediation", "owasp_name", "title", "tags", "notes"}
)

ENRICHMENT_COLUMN_FIELDS: frozenset[str] = frozenset(
    {"severity", "confidence", "description"}
)


class NormalizedFinding(NamedTuple):
    columns: dict[str, Any]
    meta: dict[str, Any]
    fingerprint: str = ""


def severity_to_rank(label: Any) -> int | None:
    """Return integer rank for a severity label, or None if invalid."""
    if label is None:
        return None
    try:
        return Severity.from_label(str(label)).rank
    except (ValueError, TypeError):
        return None


def normalise_cwe(val: Any) -> str | None:
    """Normalise a CWE value to a JSON array string, e.g. '["CWE-89"]'."""
    if val is None:
        return None
    if isinstance(val, int):
        if val <= 0:
            return None
        return json.dumps([f"CWE-{val}"])
    if isinstance(val, list):
        return json.dumps([str(v) for v in val if v])
    if isinstance(val, str) and val.startswith("["):
        return val  # already JSON array
    parts = [v.strip() for v in val.split(",") if v.strip()]
    return json.dumps(parts) if parts else None


def normalise_finding_type(val: Any) -> str | None:
    """Normalise finding_type to a JSON array string, e.g. '["secret"]'."""
    if val is None:
        return None
    if isinstance(val, str) and val.startswith("["):
        try:
            items = json.loads(val)
        except json.JSONDecodeError:
            items = [val]
    elif isinstance(val, list):
        items = val
    else:
        items = [str(val)]
    valid = [v for v in items if v in FINDING_TYPES]
    for bad in (v for v in items if v not in FINDING_TYPES):
        logger.warning("Invalid finding_type value %r; skipping", bad)
    return json.dumps(valid) if valid else None


def normalise_finding_for_insert(raw: dict) -> NormalizedFinding:
    """Normalize a raw scanner dict into (columns, meta) for storage."""
    columns: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    _PRE_EXTRACTED: frozenset[str] = frozenset(
        {
            "finding_type",
            "cwe",
            "cwe_id",
            "cwe_ids",
            "severity",
            "file_path",
            "lockfile",
            "file",
            "repo_id",
        }
    )

    columns["finding_type"] = normalise_finding_type(raw.get("finding_type"))

    raw_cwe = raw.get("cwe") or raw.get("cwe_id") or raw.get("cwe_ids")
    if raw_cwe is not None:
        columns["cwe"] = normalise_cwe(raw_cwe)

    sev_val = raw.get("severity")
    if sev_val is not None:
        columns["severity"] = severity_to_rank(sev_val)
    else:
        columns["severity"] = None

    file_val = raw.get("file_path") or raw.get("lockfile") or raw.get("file")
    if file_val is not None:
        columns["file"] = str(file_val)

    repo_id_raw = raw.get("repo_id")
    if isinstance(repo_id_raw, int):
        columns["repo_id"] = repo_id_raw
    elif isinstance(repo_id_raw, str) and repo_id_raw.isdigit():
        columns["repo_id"] = int(repo_id_raw)
    else:
        columns["repo_id"] = None

    for key, val in raw.items():
        if key in _PRE_EXTRACTED:
            continue
        if key in DIRECT_COLUMNS:
            columns[key] = val
        elif key in COMMA_LIST_FIELDS and isinstance(val, str) and val:
            meta[key] = [v.strip() for v in val.split(",") if v.strip()]
        else:
            meta[key] = val

    return NormalizedFinding(columns=columns, meta=meta)


def split_analyst_fields(
    fields: dict,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split analyst update fields into (columns, meta)."""
    columns: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    for key, val in fields.items():
        if key in ANALYST_META_KEYS:
            meta[key] = val
        else:
            columns[key] = val

    if "severity" in columns and columns["severity"] is not None:
        columns["severity"] = severity_to_rank(columns["severity"])

    return columns, meta


def split_enrichment_fields(
    fields: dict,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split LLM enrichment fields into (columns, meta). Drops unknown keys."""
    columns: dict[str, Any] = {}
    meta: dict[str, Any] = {}

    for key, val in fields.items():
        if key in ENRICHMENT_META_FIELDS:
            meta[key] = val
        elif key in ENRICHMENT_COLUMN_FIELDS:
            columns[key] = val

    if "severity" in columns and columns["severity"] is not None:
        columns["severity"] = severity_to_rank(columns["severity"])

    return columns, meta


def prepare_row_for_render(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a deserialized finding row for document rendering.

    Bridges the gap between storage-form (lists, canonical names) and the
    string/alias form that render methods expect.
    """
    prepared = dict(row)

    cwe = prepared.get("cwe")
    if isinstance(cwe, list):
        cwe_str = ", ".join(str(v) for v in cwe)
        prepared["cwe"] = cwe_str
        prepared["cwe_id"] = cwe_str
        prepared["cwe_ids"] = cwe_str
    elif cwe:
        prepared["cwe_id"] = str(cwe)
        prepared["cwe_ids"] = str(cwe)

    for key in ("tags", "aliases", "references", "finding_type"):
        val = prepared.get(key)
        if isinstance(val, list):
            prepared[key] = ", ".join(str(v) for v in val)

    return prepared


def build_triage_meta(
    confidence: str,
    reasoning: str,
    remediation: str,
    attack_vector: str | None,
    call_stack: str | None,
    access_required: str | None = None,
    exploitation_complexity: str | None = None,
    user_interaction: str | None = None,
) -> dict:
    """Build the verdict portion of meta["triage"]."""
    meta = {
        "confidence": confidence,
        "reasoning": reasoning,
        "remediation": remediation,
        "attack_vector": attack_vector,
        "call_stack": call_stack,
    }
    if access_required is not None:
        meta["access_required"] = access_required
    if exploitation_complexity is not None:
        meta["exploitation_complexity"] = exploitation_complexity
    if user_interaction is not None:
        meta["user_interaction"] = user_interaction
    return meta
