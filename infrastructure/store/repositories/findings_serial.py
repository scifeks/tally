"""Serialisation helpers for the findings table.

Contains: column-mapping constants, fingerprint logic, normalisation helpers,
and ``deserialise_row`` for converting a DB row back to a metadata dict.
No DB connection is used anywhere in this module.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from domain.findings.severity import Severity
from domain.tools.constants import FINDING_TYPES

logger = logging.getLogger(__name__)

# Named column names that map directly (field name == SQLite column name).
# "severity" is excluded because it is stored as INTEGER and requires
# int-to-label translation via Severity.from_rank() before exposure.
_DIRECT_COLUMNS: tuple[str, ...] = (
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

# Comma-joined string fields in ChromaDB → stored as JSON arrays in meta
_COMMA_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "technology",
        "subcategory",
        "references",
        "aliases",
        "tags",
    }
)


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


def deserialise_row(row: Any) -> dict[str, Any]:
    """Convert a DB row from ``search()`` into a ChromaDB-compatible metadata dict."""
    metadata: dict[str, Any] = {}

    # 1. Seed with meta blob (lowest priority)
    try:
        meta_dict: dict[str, Any] = json.loads(row["meta"] or "{}")
        metadata.update(meta_dict)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Named columns override meta (higher priority)
    for col in _DIRECT_COLUMNS:
        val = row[col]
        if val is not None:
            metadata[col] = val

    # severity: stored as INTEGER rank; translate back to label string.
    sev_val = row["severity"]
    if sev_val is not None:
        try:
            metadata["severity"] = Severity.from_rank(int(sev_val)).label
        except (ValueError, TypeError):
            metadata["severity"] = sev_val

    # Renamed + aliased columns: expose under BOTH the SQLite name
    # and the ChromaDB-compatible name so --fields works with either.
    file_val = row["file"]
    if file_val is not None:
        metadata["file"] = file_val
        metadata["file_path"] = file_val

    fp_val = row["fingerprint"]
    if fp_val is not None:
        metadata["fingerprint"] = fp_val

    rid_val = row["run_id"]
    if rid_val is not None:
        metadata["run_id"] = rid_val

    try:
        repo_id_val = row["repo_id"]
    except (IndexError, KeyError):
        repo_id_val = None
    if repo_id_val is not None:
        metadata["repo_id"] = repo_id_val

    # finding_type: stored as JSON array, return as list.
    ft_val = row["finding_type"]
    if ft_val:
        try:
            metadata["finding_type"] = json.loads(ft_val)
        except json.JSONDecodeError:
            metadata["finding_type"] = ft_val

    # cwe: stored as JSON array, return as list.
    cwe_val = row["cwe"]
    if cwe_val:
        try:
            metadata["cwe"] = json.loads(cwe_val)
        except json.JSONDecodeError:
            metadata["cwe"] = cwe_val

    metadata["enriched"] = bool(row["enriched"])

    return metadata
