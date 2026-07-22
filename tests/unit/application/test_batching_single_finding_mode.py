"""Unit tests for compute_batches() single-finding mode."""

from __future__ import annotations

from application.triage.batching import compute_batches
from tests.unit.application.conftest import _f


class TestSingleFindingMode:
    def test_isolates_every_finding(self) -> None:
        findings = [
            _f(file="src/a.py", severity="medium", line_start=1),
            _f(file="src/a.py", severity="medium", line_start=2),
            _f(file="src/a.py", severity="medium", line_start=3),
        ]
        result = compute_batches(findings, max_findings_per_batch=1)
        assert len(result) == 3
        assert all(len(b) == 1 for b in result)

    def test_no_sibling_fill(self) -> None:
        findings = [
            _f(file="src/a.py", severity="medium", line_start=1),
            _f(file="src/b.py", severity="medium", line_start=1),
        ]
        result = compute_batches(findings, max_findings_per_batch=1)
        assert len(result) == 2
        assert all(len(b) == 1 for b in result)

    def test_preserves_all_findings(self) -> None:
        findings = [
            _f(file="src/a.py", severity="critical", line_start=1),
            _f(file="src/a.py", severity="high", line_start=2),
            _f(file="src/a.py", severity="medium", line_start=3),
            _f(file="src/b.py", severity="low", line_start=1),
        ]
        result = compute_batches(findings, max_findings_per_batch=1)
        assert len(result) == 4
        all_ids = {b[0]["id"] for b in result}
        assert all_ids == {f["id"] for f in findings}

    def test_default_preserves_existing_behavior(self) -> None:
        findings = [
            _f(file="src/a.py", severity="medium", line_start=1),
            _f(file="src/a.py", severity="medium", line_start=2),
            _f(file="src/a.py", severity="medium", line_start=3),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_empty_input(self) -> None:
        assert compute_batches([], max_findings_per_batch=1) == []
