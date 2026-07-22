"""Tests for prompt assembly for LLM-based security scanning."""

from __future__ import annotations

from application.llm_scan.prompts import build_scan_prompt


class TestBuildScanPrompt:
    def test_includes_tree(self) -> None:
        tree = "src/\n  app.py\n  utils.py"
        prompt = build_scan_prompt(
            tree=tree,
            repo_name="my-repo",
            repo_path="/code/my-repo",
        )
        assert tree in prompt

    def test_includes_repo_name(self) -> None:
        prompt = build_scan_prompt(
            tree="src/",
            repo_name="my-repo",
            repo_path="/code",
        )
        assert "my-repo" in prompt

    def test_includes_output_schema(self) -> None:
        prompt = build_scan_prompt(
            tree="src/",
            repo_name="r",
            repo_path="/c",
        )
        assert "file_path" in prompt
        assert "severity" in prompt
        assert "confidence" in prompt
        assert "JSON array" in prompt

    def test_includes_severity_levels(self) -> None:
        prompt = build_scan_prompt(
            tree="src/",
            repo_name="r",
            repo_path="/c",
        )
        assert "critical" in prompt
        assert "high" in prompt
        assert "medium" in prompt
        assert "low" in prompt
        assert "informational" in prompt
