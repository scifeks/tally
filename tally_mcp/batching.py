"""Triage batching algorithm for grouping pre-sorted security findings."""

from __future__ import annotations

import os
from typing import Any

MAX_FINDINGS_PER_BATCH = 4
MAX_SIBLING_FINDINGS = 2
MAX_FILES_PER_BATCH = 2
_NO_FILL_SEVERITIES: frozenset[str] = frozenset({"critical", "high"})


def _severity_allows_fill(severity: str | None) -> bool:
    return severity not in _NO_FILL_SEVERITIES


def _file_dir(file: str | None) -> str | None:
    """Return dirname, or None if file is None or has no directory component."""
    if not file:
        return None
    d = os.path.dirname(file)
    return d if d else None


def _are_siblings(file_a: str | None, file_b: str | None) -> bool:
    """True if both files are in the same non-root directory."""
    dir_a = _file_dir(file_a)
    dir_b = _file_dir(file_b)
    return dir_a is not None and dir_a == dir_b


def _fill_siblings(
    batch: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    primary_file: str | None,
    primary_rt: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Try to fill batch with sibling findings.

    Returns (updated_batch, updated_queue).
    """
    # 2-file decay: with 2 files, max total = 3
    available = min(MAX_SIBLING_FINDINGS, 3 - len(batch))
    if available <= 0:
        return batch, queue

    # Candidate siblings: same directory, different file
    sibling_candidates = [
        f
        for f in queue
        if _are_siblings(f.get("file"), primary_file) and f.get("file") != primary_file
    ]

    if not sibling_candidates:
        return batch, queue

    # Prefer same risk_type; fall back to any sibling rt
    same_rt = [f for f in sibling_candidates if f.get("risk_type") == primary_rt]
    pool = same_rt if same_rt else sibling_candidates

    # Pick ONE sibling file (first one in pool order)
    sibling_file = pool[0].get("file")
    pool = [f for f in pool if f.get("file") == sibling_file]

    taken = pool[:available]
    taken_ids = {f["id"] for f in taken}
    new_queue = [f for f in queue if f.get("id") not in taken_ids]
    return batch + taken, new_queue


def compute_batches(findings: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group pre-sorted findings into triage batches.

    Input must be scoped to a single tool+repo (asserted, not enforced).
    Findings are expected pre-sorted: severity DESC, file, risk_type, line_start ASC.
    Returns a list of batches; each batch is a list of finding dicts, unchanged.
    """
    if not findings:
        return []

    queue: list[dict[str, Any]] = list(findings)
    batches: list[list[dict[str, Any]]] = []

    while queue:
        anchor = queue[0]
        anchor_file = anchor.get("file")
        anchor_rt = anchor.get("risk_type")
        anchor_sev = anchor.get("severity")

        # Extract consecutive cluster from front of queue (same file+risk_type)
        cluster: list[dict[str, Any]] = []
        rest: list[dict[str, Any]] = []
        consuming = True
        for f in queue:
            if (
                consuming
                and f.get("file") == anchor_file
                and f.get("risk_type") == anchor_rt
            ):
                cluster.append(f)
            else:
                consuming = False
                rest.append(f)
        queue = rest

        if len(cluster) > MAX_FINDINGS_PER_BATCH:
            # Oversized cluster: split into chunks of MAX_FINDINGS_PER_BATCH
            for i in range(0, len(cluster), MAX_FINDINGS_PER_BATCH):
                batches.append(cluster[i : i + MAX_FINDINGS_PER_BATCH])
            continue

        batch = list(cluster)

        if _severity_allows_fill(anchor_sev) and len(batch) < MAX_FINDINGS_PER_BATCH:
            batch, queue = _fill_siblings(batch, queue, anchor_file, anchor_rt)

        batches.append(batch)

    return batches
