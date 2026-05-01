"""Unit tests for application.reporting.attack_surface.AttackSurfaceBuilder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.attack_surface import (  # noqa: E402
    AttackSurfaceBuilder,
)
from domain.findings.entry import Finding  # noqa: E402


def _make_finding(**kwargs: Any) -> Finding:
    defaults: dict[str, Any] = {
        "id": 0,
        "fingerprint": None,
        "run_id": None,
        "tool": None,
        "domain": None,
        "segment": None,
    }
    defaults.update(kwargs)
    return Finding(**defaults)


class TestAttackSurfaceBuilder(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = MagicMock()
        self.builder = AttackSurfaceBuilder(self.repo)

    # ------------------------------------------------------------------ #
    # Repository surface
    # ------------------------------------------------------------------ #

    def test_repo_empty_findings(self) -> None:
        result = self.builder.build([])
        self.assertIn("No triaged findings available", result)

    def test_repo_single_repo_multiple_segments(self) -> None:
        findings = [
            _make_finding(meta={"repo": "myrepo"}, segment="sast"),
            _make_finding(meta={"repo": "myrepo"}, segment="secrets"),
        ]
        result = self.builder.build(findings)
        self.assertIn("myrepo", result)
        self.assertIn("&#x2713;", result)
        self.assertIn("&#x2014;", result)

    def test_repo_multiple_repos_sorted(self) -> None:
        findings = [
            _make_finding(meta={"repo": "repo-b"}, segment="sast"),
            _make_finding(meta={"repo": "repo-a"}, segment="sca"),
        ]
        result = self.builder.build(findings)
        idx_a = result.index("repo-a")
        idx_b = result.index("repo-b")
        self.assertLess(idx_a, idx_b)

    def test_repo_null_repo(self) -> None:
        findings = [_make_finding(meta={}, segment="sast")]
        result = self.builder.build(findings)
        self.assertIn("Unattributed", result)

    def test_repo_no_segments(self) -> None:
        findings = [_make_finding(meta={"repo": "some-repo"}, segment="")]
        result = self.builder.build(findings)
        self.assertIn("No repository surface data available", result)

    # ------------------------------------------------------------------ #
    # Dependency surface
    # ------------------------------------------------------------------ #

    def test_dep_no_sca_findings(self) -> None:
        findings = [
            _make_finding(tool="semgrep", meta={"repo": "backend"}, segment="sast"),
        ]
        result = self.builder.build(findings)
        self.assertIn("Dependency scanning data is not available", result)

    def test_dep_sca_with_ecosystems(self) -> None:
        findings = [
            _make_finding(
                tool="pip-audit",
                meta={"repo": "my-app"},
                ecosystem="PyPI",
                segment="sca",
            ),
            _make_finding(
                tool="npm-audit",
                meta={"repo": "my-app"},
                ecosystem="npm",
                segment="sca",
            ),
        ]
        result = self.builder.build(findings)
        self.assertIn("my-app", result)
        self.assertIn("PyPI", result)
        self.assertIn("npm", result)

    def test_dep_deduplication(self) -> None:
        findings = [
            _make_finding(
                tool="pip-audit",
                meta={"repo": "app"},
                ecosystem="PyPI",
                segment="sca",
            ),
            _make_finding(
                tool="pip-audit",
                meta={"repo": "app"},
                ecosystem="PyPI",
                segment="sca",
            ),
        ]
        result = self.builder.build(findings)
        self.assertEqual(result.count("PyPI"), 1)

    def test_dep_empty_ecosystem(self) -> None:
        findings = [
            _make_finding(
                tool="pip-audit",
                meta={"repo": "app"},
                ecosystem="",
                segment="sca",
            ),
        ]
        result = self.builder.build(findings)
        self.assertIn("No ecosystem data found", result)

    def test_dep_sorted_pairs(self) -> None:
        findings = [
            _make_finding(
                tool="pip-audit",
                meta={"repo": "z-repo"},
                ecosystem="PyPI",
                segment="sca",
            ),
            _make_finding(
                tool="npm-audit",
                meta={"repo": "a-repo"},
                ecosystem="npm",
                segment="sca",
            ),
        ]
        result = self.builder.build(findings)
        idx_a = result.index("a-repo")
        idx_z = result.index("z-repo")
        self.assertLess(idx_a, idx_z)
