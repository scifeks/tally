"""Unit tests for compute_batches(). Sibling fill rules."""

from __future__ import annotations

from application.triage.batching import compute_batches
from tests.unit.application.conftest import _f


class TestSiblingFill:
    def test_medium_sibling_fill_same_rt(self) -> None:
        # Medium anchor + sibling in same dir + same rt → sibling pulled in
        anchor = _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1)
        sibling = _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1)
        findings = [anchor, sibling]
        result = compute_batches(findings)
        # Should end up in one batch
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_sibling_fill_falls_back_to_adjacent_rt(self) -> None:
        # Same dir but different risk_type → still taken as fallback
        anchor = _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1)
        sibling = _f(file="src/b.py", severity="medium", risk_type="xss", line_start=1)
        findings = [anchor, sibling]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_two_file_batch_max_three(self) -> None:
        # anchor cluster of 2 → batch closes (no sibling slot), sibling in own batch
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=2),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        first_batch_files = {f["file"] for f in result[0]}
        assert first_batch_files == {"src/a.py"}

    def test_never_more_than_two_files(self) -> None:
        # Three sibling files available; batch should contain at most 2 distinct files
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/c.py", severity="medium", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        first_batch = result[0]
        files_in_batch = {f["file"] for f in first_batch}
        assert len(files_in_batch) <= 2

    def test_directory_boundary_respected(self) -> None:
        # Files in different directories are never siblings
        anchor = _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1)
        other = _f(file="lib/b.py", severity="medium", risk_type="sqli", line_start=1)
        findings = [anchor, other]
        result = compute_batches(findings)
        # Different dirs → no fill → separate batches
        assert len(result) == 2

    def test_case4_one_medium_finding_with_sibling(self) -> None:
        # 1 medium on src/a.py, 1 medium on src/b.py → pulled into same batch
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_case5_two_medium_findings_no_sibling_slot(self) -> None:
        # 2 medium on src/a.py → chunk of 2, no sibling slot → sibling gets own batch
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=2),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert {f["file"] for f in result[0]} == {"src/a.py"}
        assert result[1][0]["file"] == "src/b.py"

    def test_case7_two_siblings_same_rt_one_batch(self) -> None:
        # 1 medium on src/a.py, 2 on src/b.py (same rt)
        # src/b.py has 2 queue entries → not eligible for sibling fill
        # Expected: src/a.py alone, src/b.py alone (2 findings)
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert {f["file"] for f in result[0]} == {"src/a.py"}
        assert len(result[0]) == 1
        assert {f["file"] for f in result[1]} == {"src/b.py"}
        assert len(result[1]) == 2

    def test_case8_two_siblings_different_rt_fallback(self) -> None:
        # 1 medium sqli on src/a.py, sibling has xss → fallback takes it
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="xss", line_start=1),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 2

    def test_case9_different_directories_never_grouped(self) -> None:
        # src/a.py and lib/b.py are in different dirs → never grouped
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="lib/b.py", severity="medium", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert result[0][0]["file"] == "src/a.py"
        assert result[1][0]["file"] == "lib/b.py"

    def test_case11_three_siblings_first_two_batch_together(self) -> None:
        # 1 medium on src/a.py, siblings on src/b.py and src/c.py
        # Only 1 sibling taken (MAX_SIBLING_FINDINGS=1), first in queue order
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/c.py", severity="medium", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        first_batch = result[0]
        assert len(first_batch) == 2
        assert first_batch[0]["file"] == "src/a.py"
        assert first_batch[1]["file"] == "src/b.py"

    def test_sibling_with_multi_finding_file_does_not_fill(self) -> None:
        # src/a.py: 1 medium finding; src/b.py: 2 medium findings (same dir)
        # src/b.py has 2 queue entries; not eligible for sibling fill
        # Expected: 2 batches; src/a.py alone, src/b.py with both its findings
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert {f["file"] for f in result[0]} == {"src/a.py"}
        assert len(result[0]) == 1
        assert {f["file"] for f in result[1]} == {"src/b.py"}
        assert len(result[1]) == 2
