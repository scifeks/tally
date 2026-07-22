"""Tests for semgrep --include support."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.tools.wrappers.base.semgrep import BaseSemgrepTool
from infrastructure.tools.wrappers.local.semgrep import SemgrepLocalTool


class TestSemgrepInclude:
    @pytest.fixture(autouse=True)
    def _fake_repo(self, tmp_path: Path) -> None:
        self.repo = str(tmp_path)

    def test_include_adds_flags(self) -> None:
        tool = SemgrepLocalTool()
        cmd = tool.build_command(
            repo_path=self.repo,
            include=["src/foo.py", "src/bar.py"],
        )
        idx = cmd.index("--include")
        assert cmd[idx + 1] == "src/foo.py"
        idx2 = cmd.index("--include", idx + 1)
        assert cmd[idx2 + 1] == "src/bar.py"

    def test_no_include_omits_flag(self) -> None:
        tool = SemgrepLocalTool()
        cmd = tool.build_command(repo_path=self.repo)
        assert "--include" not in cmd

    def test_supports_include_attribute(self) -> None:
        assert BaseSemgrepTool.supports_include is True
