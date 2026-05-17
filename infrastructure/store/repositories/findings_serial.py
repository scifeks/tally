"""Deserialization helpers for the findings table."""

from __future__ import annotations

import json
from typing import Any

from domain.findings.normalization import DIRECT_COLUMNS as _DIRECT_COLUMNS
from domain.findings.severity import Severity


def deserialise_row(row: Any) -> dict[str, Any]:
    """Convert a DB row from ``search()`` into a ChromaDB-compatible metadata dict."""
    metadata: dict[str, Any] = {}

    # Meta blob is lowest priority; named columns override below.
    try:
        meta_dict: dict[str, Any] = json.loads(row["meta"] or "{}")
        metadata.update(meta_dict)
    except (json.JSONDecodeError, TypeError):
        pass

    for col in _DIRECT_COLUMNS:
        val = row[col]
        if val is not None:
            metadata[col] = val

    sev_val = row["severity"]
    if sev_val is not None:
        try:
            metadata["severity"] = Severity.from_rank(int(sev_val)).label
        except (ValueError, TypeError):
            metadata["severity"] = sev_val

    # Expose both names so --fields accepts either convention.
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

    ft_val = row["finding_type"]
    if ft_val:
        try:
            metadata["finding_type"] = json.loads(ft_val)
        except json.JSONDecodeError:
            metadata["finding_type"] = ft_val

    cwe_val = row["cwe"]
    if cwe_val:
        try:
            metadata["cwe"] = json.loads(cwe_val)
        except json.JSONDecodeError:
            metadata["cwe"] = cwe_val

    metadata["enriched"] = bool(row["enriched"])

    return metadata
