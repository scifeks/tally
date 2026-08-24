"""Tests for gitleaks TOML config generation."""

import re

from infrastructure.tools.wrappers.base.gitleaks import (
    _build_gitleaks_toml,
)


class TestBuildGitleaksToml:
    def test_regex_matches_case_insensitively(self) -> None:
        toml = _build_gitleaks_toml(["tests", "vendor"], None)

        for path in [
            "tests/foo.py",
            "Tests/foo.py",
            "src/tests/bar.py",
            "src/Tests/bar.py",
            "vendor/lib.php",
            "Vendor/lib.php",
        ]:
            matched = self._path_matches_toml(toml, path)
            assert matched, f"{path} not matched"

    def test_empty_dirs_returns_extend_only(self) -> None:
        toml = _build_gitleaks_toml([], None)
        assert "allowlists" not in toml

    def _path_matches_toml(self, toml: str, path: str) -> bool:
        block = re.search(r"paths\s*=\s*\[(.*?)\]", toml, re.DOTALL)
        if not block:
            return False
        for line in block.group(1).strip().split("\n"):
            raw = line.strip().strip(",").strip("'")
            if not raw:
                continue
            if re.search(raw, path):
                return True
        return False
