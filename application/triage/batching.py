"""Triage batching algorithm for grouping pre-sorted security findings."""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

MAX_SAME_FILE_FINDINGS = 3
MAX_SIBLING_FINDINGS = 1
MAX_FILES_PER_BATCH = 2
MAX_FINDINGS_PER_BATCH = 4
WEB_FINDINGS_PER_BATCH = 1
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


def _split_consecutive_by_file(
    queue: list[dict[str, Any]], anchor_file: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract leading consecutive findings that match anchor_file."""
    cluster: list[dict[str, Any]] = []
    rest: list[dict[str, Any]] = []
    consuming = True
    for f in queue:
        if consuming and f.get("file") == anchor_file:
            cluster.append(f)
        else:
            consuming = False
            rest.append(f)
    return cluster, rest


def _fill_siblings(
    batch: list[dict[str, Any]],
    queue: list[dict[str, Any]],
    primary_file: str | None,
    primary_rt: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Try to fill a single-finding batch with one sibling finding.

    Only called when the primary file contributes exactly 1 finding.
    Returns (updated_batch, updated_queue).
    """
    # Candidate siblings: same directory, different file, fill-eligible severity,
    # and that file appears exactly once in the queue (multi-finding files anchor
    # their own batches and must not donate a finding here).
    file_counts = Counter(f.get("file") for f in queue)

    sibling_candidates = [
        f
        for f in queue
        if _are_siblings(f.get("file"), primary_file)
        and f.get("file") != primary_file
        and _severity_allows_fill(f.get("severity"))
        and file_counts[f.get("file")] == 1
    ]

    if not sibling_candidates:
        return batch, queue

    # Prefer same risk_type; fall back to any eligible sibling
    same_rt = [f for f in sibling_candidates if f.get("risk_type") == primary_rt]
    pool = same_rt if same_rt else sibling_candidates

    # Pick ONE sibling file (first one in pool order)
    sibling_file = pool[0].get("file")
    pool = [f for f in pool if f.get("file") == sibling_file]

    taken = pool[:MAX_SIBLING_FINDINGS]
    taken_ids = {f["id"] for f in taken}
    new_queue = [f for f in queue if f.get("id") not in taken_ids]
    return batch + taken, new_queue


def compute_batches(
    findings: list[dict[str, Any]],
    *,
    max_findings_per_batch: int = MAX_FINDINGS_PER_BATCH,
) -> list[list[dict[str, Any]]]:
    """Group pre-sorted findings into triage batches.

    Input must be scoped to a single tool+repo (asserted, not enforced).
    Findings are expected pre-sorted: severity DESC, file, line_start ASC.
    Returns a list of batches; each batch is a list of finding dicts, unchanged.
    """
    if not findings:
        return []

    if max_findings_per_batch <= 1:
        return [[f] for f in findings]

    queue: list[dict[str, Any]] = list(findings)
    batches: list[list[dict[str, Any]]] = []

    while queue:
        anchor_file = queue[0].get("file")

        cluster, queue = _split_consecutive_by_file(queue, anchor_file)

        # Critical/high findings get isolated batches to avoid diluting triage focus
        no_fill = [f for f in cluster if f.get("severity") in _NO_FILL_SEVERITIES]
        fill = [f for f in cluster if f.get("severity") not in _NO_FILL_SEVERITIES]

        for f in no_fill:
            batches.append([f])

        for i in range(0, len(fill), MAX_SAME_FILE_FINDINGS):
            chunk = fill[i : i + MAX_SAME_FILE_FINDINGS]
            if len(chunk) == 1:
                primary_rt = chunk[0].get("risk_type")
                chunk, queue = _fill_siblings(chunk, queue, anchor_file, primary_rt)
            batches.append(chunk)

    return batches


def batch_size_for_segment(
    segment: str,
    *,
    default: int = MAX_FINDINGS_PER_BATCH,
) -> int:
    """Return the batch size limit for a finding segment."""
    if segment == "web":
        return WEB_FINDINGS_PER_BATCH
    return default
