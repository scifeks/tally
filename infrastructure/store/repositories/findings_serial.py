"""Serialisation helpers for the findings table.

Contains: column-mapping constants, fingerprint logic, normalisation helpers,
and ``deserialise_row`` for converting a DB row back to a metadata dict.
No DB connection is used anywhere in this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from domain.tools.constants import FINDING_TYPES
from infrastructure.tools.fingerprints import FINGERPRINT_REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------

# ChromaDB field name → SQLite named column name
_CHROMA_TO_SQLITE: dict[str, str] = {
    "tool": "tool",
    "domain": "domain",
    "segment": "segment",
    "repo": "repo",
    "finding_type": "finding_type",
    "severity": "severity",
    "confidence": "confidence",
    "file_path": "file",
    "rule_id": "rule_id",
    "url": "url",
    "ip_address": "host",
    "port": "port",
    "vulnerability_id": "vulnerability_id",
    "package_name": "package_name",
    "ecosystem": "ecosystem",
    "description": "description",
    "package_version": "package_version",
    "lockfile": "file",  # SCA: lower priority than file_path
}

# Named column names that are identical in ChromaDB and SQLite
_DIRECT_COLUMNS: tuple[str, ...] = (
    "tool",
    "domain",
    "segment",
    "repo",
    "severity",
    "confidence",
    "rule_id",
    "url",
    "port",
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
        "ssh_algorithms",
    }
)

# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def _generic_fingerprint_key(finding: dict[str, Any]) -> str:
    safe = {
        k: v for k, v in sorted(finding.items()) if isinstance(v, (str, int, float))
    }
    return json.dumps(safe, sort_keys=True)


def compute_fingerprint(finding: dict[str, Any]) -> str:
    """Compute a stable sha256 fingerprint from per-tool key fields."""
    tool = finding.get("tool", "")
    key_fn = FINGERPRINT_REGISTRY.get(tool, _generic_fingerprint_key)
    key = key_fn(finding)
    return hashlib.sha256(key.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


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
        return json.dumps([f"CWE-{val}"])
    if isinstance(val, list):
        return json.dumps([str(v) for v in val if v])
    if isinstance(val, str) and val.startswith("["):
        return val  # already JSON array
    parts = [v.strip() for v in val.split(",") if v.strip()]
    return json.dumps(parts) if parts else None


# ---------------------------------------------------------------------------
# Row deserialisation
# ---------------------------------------------------------------------------


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

    # Renamed + aliased columns: expose under BOTH the SQLite name
    # and the ChromaDB-compatible name so --fields works with either.
    file_val = row["file"]
    if file_val is not None:
        metadata["file"] = file_val
        metadata["file_path"] = file_val

    host_val = row["host"]
    if host_val is not None:
        metadata["host"] = host_val
        metadata["ip_address"] = host_val

    fp_val = row["fingerprint"]
    if fp_val is not None:
        metadata["fingerprint"] = fp_val

    rid_val = row["run_id"]
    if rid_val is not None:
        metadata["run_id"] = rid_val

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
