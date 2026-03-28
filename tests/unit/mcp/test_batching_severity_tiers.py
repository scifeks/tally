"""Unit tests for compute_batches() — severity tiers and no-fill rules."""

from __future__ import annotations

from application.triage.batching import compute_batches
from tests.unit.mcp.conftest import _f


class TestSeverityTiers:
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
