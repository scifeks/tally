"""Cross-repo uniqueness tests for fingerprint key functions."""

from __future__ import annotations

from infrastructure.tools.fingerprints import (
    _gitleaks_fingerprint_key,
    _noir_fingerprint_key,
    _sca_fingerprint_key,
    _semgrep_fingerprint_key,
    _zap_fingerprint_key,
)


class TestCrossRepoUniqueness:
    """Same finding in two different repos must produce different keys."""

    def test_gitleaks_different_repos_produce_different_keys(self) -> None:
        base = {
            "rule_id": "aws-key",
            "file_path": "/src/config.py",
            "line_number": 10,
        }
        key_a = _gitleaks_fingerprint_key({**base, "repo": "repo-a"})
        key_b = _gitleaks_fingerprint_key({**base, "repo": "repo-b"})
        assert key_a != key_b

    def test_semgrep_different_repos_produce_different_keys(self) -> None:
        base = {"rule_id": "sqli", "file_path": "app.py", "line_start": 42}
        key_a = _semgrep_fingerprint_key({**base, "repo": "repo-a"})
        key_b = _semgrep_fingerprint_key({**base, "repo": "repo-b"})
        assert key_a != key_b

    def test_zap_different_repos_produce_different_keys(self) -> None:
        base = {"url": "/login", "method": "POST", "alert_name": "SQLi"}
        key_a = _zap_fingerprint_key({**base, "repo": "repo-a"})
        key_b = _zap_fingerprint_key({**base, "repo": "repo-b"})
        assert key_a != key_b

    def test_sca_different_repos_produce_different_keys(self) -> None:
        base = {
            "package_name": "lodash",
            "vulnerability_id": "CVE-2021-23337",
            "ecosystem": "npm",
        }
        key_a = _sca_fingerprint_key("npm-audit", {**base, "repo": "repo-a"})
        key_b = _sca_fingerprint_key("npm-audit", {**base, "repo": "repo-b"})
        assert key_a != key_b

    def test_noir_different_repos_produce_different_keys(self) -> None:
        base = {"method": "GET", "url": "/api/users"}
        key_a = _noir_fingerprint_key({**base, "repo": "repo-a"})
        key_b = _noir_fingerprint_key({**base, "repo": "repo-b"})
        assert key_a != key_b

    def test_same_repo_same_finding_produces_identical_key(self) -> None:
        finding = {
            "repo": "repo-a",
            "rule_id": "aws-key",
            "file_path": "/src/config.py",
            "line_number": 10,
        }
        assert _gitleaks_fingerprint_key(finding) == _gitleaks_fingerprint_key(finding)
