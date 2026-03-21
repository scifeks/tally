"""Unit tests for compute_batches() — file clustering and ceiling rules."""

from __future__ import annotations

from tally_mcp.batching import compute_batches
from tests.unit.mcp.conftest import _f


class TestFileClustering:
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

    def test_risk_type_none_own_group(self) -> None:
        # risk_type=None and named risk types now grouped together by file
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type=None, line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 1
        assert len(result[0]) == 2

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
