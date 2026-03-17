"""Unit tests for tally_mcp.batching.compute_batches()."""

from __future__ import annotations

import sys
from pathlib import Path

_TALLY_ROOT = Path(__file__).resolve().parents[2]
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
        # 6 findings same file+rt → 2 batches of 4 and 2
        findings = [
            _f(file="src/a.py", risk_type="sqli", line_start=i) for i in range(1, 7)
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        assert len(result[0]) == 4
        assert len(result[1]) == 2

    def test_single_file_multiple_rt_groups(self) -> None:
        # 2 risk_types on same file → separate batches
        findings = [
            _f(file="src/a.py", risk_type="sqli", line_start=1),
            _f(file="src/a.py", risk_type="sqli", line_start=2),
            _f(file="src/a.py", risk_type="xss", line_start=3),
            _f(file="src/a.py", risk_type="xss", line_start=4),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        for batch in result:
            rts = {f["risk_type"] for f in batch}
            assert len(rts) == 1

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
        # anchor cluster of 2 + sibling fill → max 3 total (2-file decay)
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=2),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/b.py", severity="medium", risk_type="sqli", line_start=2),
        ]
        result = compute_batches(findings)
        first_batch = result[0]
        assert len(first_batch) <= 3

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
        # risk_type=None clusters separately from named risk types
        findings = [
            _f(file="src/a.py", severity="medium", risk_type="sqli", line_start=1),
            _f(file="src/a.py", severity="medium", risk_type=None, line_start=2),
        ]
        result = compute_batches(findings)
        assert len(result) == 2
        rt_values = [b[0]["risk_type"] for b in result]
        assert "sqli" in rt_values
        assert None in rt_values
