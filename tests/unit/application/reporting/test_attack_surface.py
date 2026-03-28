"""Unit tests for application.reporting.attack_surface.AttackSurfaceBuilder."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.attack_surface import (  # noqa: E402
    AttackSurfaceBuilder,
)


class TestAttackSurfaceBuilder(unittest.TestCase):
    """Tests for AttackSurfaceBuilder.build() and its private helpers."""

    def setUp(self) -> None:
        self.repo = MagicMock()
        self.builder = AttackSurfaceBuilder(self.repo)
        self.repo.get_all_nmap_findings.return_value = []

    # ------------------------------------------------------------------ #
    # Network surface
    # ------------------------------------------------------------------ #

    def test_network_empty(self) -> None:
        result = self.builder.build([])
        self.assertIn("Network scanning data is not available", result)

    def test_network_single_host_single_port(self) -> None:
        self.repo.get_all_nmap_findings.return_value = [
            {
                "host": "192.168.1.1",
                "port": 80,
                "meta": (
                    '{"transport": "tcp",'
                    ' "service": "http",'
                    ' "service_version": "Apache 2.4"}'
                ),
            }
        ]
        result = self.builder.build([])
        self.assertIn("192.168.1.1", result)
        self.assertIn("<td>80</td>", result)
        self.assertIn("<td>tcp</td>", result)
        self.assertIn("<td>http</td>", result)
        self.assertIn("<td>Apache 2.4</td>", result)

    def test_network_multiple_hosts_ports(self) -> None:
        self.repo.get_all_nmap_findings.return_value = [
            {"host": "192.168.1.1", "port": 80, "meta": "{}"},
            {"host": "192.168.1.1", "port": 22, "meta": "{}"},
            {"host": "10.0.0.1", "port": 443, "meta": "{}"},
        ]
        result = self.builder.build([])
        self.assertIn("192.168.1.1", result)
        self.assertIn("10.0.0.1", result)
        # Port 22 should appear before port 80 (sorted ascending)
        idx_22 = result.index("<td>22</td>")
        idx_80 = result.index("<td>80</td>")
        self.assertLess(idx_22, idx_80)

    def test_network_meta_as_dict(self) -> None:
        self.repo.get_all_nmap_findings.return_value = [
            {
                "host": "10.1.1.1",
                "port": 8080,
                "meta": {
                    "transport": "tcp",
                    "service": "http-proxy",
                    "service_version": "Squid 4",
                },
            }
        ]
        result = self.builder.build([])
        self.assertIn("10.1.1.1", result)
        self.assertIn("<td>8080</td>", result)
        self.assertIn("<td>http-proxy</td>", result)
        self.assertIn("<td>Squid 4</td>", result)

    def test_network_missing_host(self) -> None:
        self.repo.get_all_nmap_findings.return_value = [
            {"host": None, "port": 22, "meta": "{}"},
        ]
        result = self.builder.build([])
        self.assertIn("unknown", result)

    # ------------------------------------------------------------------ #
    # Repository surface
    # ------------------------------------------------------------------ #

    def test_repo_empty_findings(self) -> None:
        result = self.builder.build([])
        self.assertIn("No triaged findings available", result)

    def test_repo_single_repo_multiple_segments(self) -> None:
        findings = [
            {"repo": "myrepo", "segment": "sast"},
            {"repo": "myrepo", "segment": "secrets"},
        ]
        result = self.builder.build(findings)
        self.assertIn("myrepo", result)
        # SAST and Secrets present => checkmark
        self.assertIn("&#x2713;", result)
        # SCA and DAST absent => em-dash
        self.assertIn("&#x2014;", result)

    def test_repo_multiple_repos_sorted(self) -> None:
        findings = [
            {"repo": "repo-b", "segment": "sast"},
            {"repo": "repo-a", "segment": "sca"},
        ]
        result = self.builder.build(findings)
        idx_a = result.index("repo-a")
        idx_b = result.index("repo-b")
        self.assertLess(idx_a, idx_b)

    def test_repo_null_repo(self) -> None:
        findings = [{"repo": None, "segment": "sast"}]
        result = self.builder.build(findings)
        self.assertIn("Unattributed", result)

    def test_repo_no_segments(self) -> None:
        findings = [{"repo": "some-repo", "segment": ""}]
        result = self.builder.build(findings)
        self.assertIn("No repository surface data available", result)

    # ------------------------------------------------------------------ #
    # Dependency surface
    # ------------------------------------------------------------------ #

    def test_dep_no_sca_findings(self) -> None:
        findings = [{"tool": "semgrep", "repo": "backend", "segment": "sast"}]
        result = self.builder.build(findings)
        self.assertIn("Dependency scanning data is not available", result)

    def test_dep_sca_with_ecosystems(self) -> None:
        findings = [
            {
                "tool": "pip-audit",
                "repo": "my-app",
                "ecosystem": "PyPI",
                "segment": "sca",
            },
            {
                "tool": "npm-audit",
                "repo": "my-app",
                "ecosystem": "npm",
                "segment": "sca",
            },
        ]
        result = self.builder.build(findings)
        self.assertIn("my-app", result)
        self.assertIn("PyPI", result)
        self.assertIn("npm", result)

    def test_dep_deduplication(self) -> None:
        findings = [
            {"tool": "pip-audit", "repo": "app", "ecosystem": "PyPI", "segment": "sca"},
            {"tool": "pip-audit", "repo": "app", "ecosystem": "PyPI", "segment": "sca"},
        ]
        result = self.builder.build(findings)
        # The (app, PyPI) pair should appear exactly once
        self.assertEqual(result.count("PyPI"), 1)

    def test_dep_empty_ecosystem(self) -> None:
        findings = [
            {"tool": "pip-audit", "repo": "app", "ecosystem": "", "segment": "sca"},
        ]
        result = self.builder.build(findings)
        self.assertIn("No ecosystem data found", result)

    def test_dep_sorted_pairs(self) -> None:
        findings = [
            {
                "tool": "pip-audit",
                "repo": "z-repo",
                "ecosystem": "PyPI",
                "segment": "sca",
            },
            {
                "tool": "npm-audit",
                "repo": "a-repo",
                "ecosystem": "npm",
                "segment": "sca",
            },
        ]
        result = self.builder.build(findings)
        idx_a = result.index("a-repo")
        idx_z = result.index("z-repo")
        self.assertLess(idx_a, idx_z)
