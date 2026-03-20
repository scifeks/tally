"""Unit tests for tally_mcp.batching.compute_batches()."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tally_mcp.batching import compute_batches  # noqa: E402

# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

_next_id = 0


def _f(
    file: str = "src/a.py",
    severity: str = "medium",
    risk_type: str | None = "sqli",
    line_start: int = 1,
    tool: str = "semgrep",
    repo: str = "myrepo",
    **kwargs: object,
) -> dict:
    global _next_id
    _next_id += 1
    return {
        "id": _next_id,
        "tool": tool,
        "repo": repo,
        "file": file,
        "severity": severity,
        "risk_type": risk_type,
        "line_start": line_start,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComputeBatches:
    def test_empty_input(self) -> None:
        assert compute_batches([]) == []

    def test_single_finding(self) -> None:
        findings = [_f()]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 1

    def test_single_file_single_rt_under_ceiling(self) -> None:
        # 3 findings: same file + risk_type → one batch
        findings = [
            _f(file="src/a.py", risk_type="sqli", line_start=1),
            _f(file="src/a.py", risk_type="sqli", line_start=2),
            _f(file="src/a.py", risk_type="sqli", line_start=3),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_single_file_single_rt_over_ceiling(self) -> None:
        # 6 findings same file+rt → 2 batches of 3 each
        findings = [
            _f(file="src/a.py", risk_type="sqli", line_start=i) for i in range(1, 7)
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert len(result[0]) == 3
        assert len(result[1]) == 3

    def test_single_file_multiple_rt_groups(self) -> None:
        # 2 risk_types on same file → grouped by file, 1 batch of 3 + 1 batch of 1
        findings = [
            _f(file="src/a.py", risk_type="sqli", line_start=1),
            _f(file="src/a.py", risk_type="sqli", line_start=2),
            _f(file="src/a.py", risk_type="xss", line_start=3),
            _f(file="src/a.py", risk_type="xss", line_start=4),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert len(result[0]) == 3
        assert len(result[1]) == 1

    def test_critical_no_sibling_fill(self) -> None:
        # Critical anchor should NOT pull in siblings
        sibling = _f(
            file="src/b.py", severity="critical", risk_type="sqli", line_start=1
        )
        anchor = _f(
            file="src/a.py", severity="critical", risk_type="sqli", line_start=1
        )
        findings = [anchor, sibling]
        result = compute_batches(findings)
        # Each should be in its own batch
        assert len(result) == 2
        assert all(len(b) == 1 for b in result)

    def test_high_no_sibling_fill(self) -> None:
        # High anchor should NOT pull in siblings
        sibling = _f(file="src/b.py", severity="high", risk_type="sqli", line_start=1)
        anchor = _f(file="src/a.py", severity="high", risk_type="sqli", line_start=1)
        findings = [anchor, sibling]
        result = compute_batches(findings)
        assert len(result) == 2
        assert all(len(b) == 1 for b in result)

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

    def test_risk_type_none_own_group(self) -> None:
        # risk_type=None and named risk types now grouped together by file
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type=None, line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 2

    # -----------------------------------------------------------------------
    # New spec cases
    # -----------------------------------------------------------------------

    def test_case1_same_file_mixed_rt_three_medium_one_batch(self) -> None:
        # 3 medium findings on same file with different risk_types → 1 batch
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type="xss", line_start=2),
            _f(file="src/a.py", severity="medium", risk_type="rce", line_start=3),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 3

    def test_case2_same_file_mixed_severity_tiers(self) -> None:
        # 1 high + 2 medium on same file → 1 batch for high, 1 batch for 2 medium
        findings = [
            _f(file="src/a.py", severity="high", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type="xss", line_start=2),
            _f(file="src/a.py", severity="medium", risk_type="rce", line_start=3),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        high_batches = [b for b in result if b[0]["severity"] == "high"]
        med_batches = [b for b in result if b[0]["severity"] != "high"]
        assert len(high_batches) == 1
        assert len(high_batches[0]) == 1
        assert len(med_batches) == 1
        assert len(med_batches[0]) == 2

    def test_case3_same_file_all_high_one_per_batch(self) -> None:
        # 3 high findings on same file → 3 separate batches
        findings = [
            _f(file="src/a.py", severity="high", risk_type="sqli", line_start=i)
            for i in range(1, 4)
        ]
        result = compute_batches(findings)
        assert len(result) == 3
        assert all(len(b) == 1 for b in result)

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

    def test_case6_four_medium_findings_two_batches(self) -> None:
        # 4 medium findings on src/a.py → 2 batches of 3 and 1
        # The lone finding may get a sibling if available; here no sibling
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=i)
            for i in range(1, 5)
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert len(result[0]) == 3
        assert len(result[1]) == 1

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

    def test_case10_sibling_fill_skips_no_fill_tier(self) -> None:
        # 1 medium on src/a.py, sibling is high on src/b.py → high not eligible
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="high", risk_type="sqli", line_start=1),
        ]
        result = compute_batches(findings)
        # high sibling not eligible → no fill → 2 separate batches
        # (high processed second as its own batch)
        assert len(result) == 2

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
        # src/b.py has 2 queue entries → not eligible for sibling fill
        # Expected: 2 batches — src/a.py alone, src/b.py with both its findings
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
