"""Integration tests for gitleaks binary round-trip (requires gitleaks binary)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.rag.ingestor import ToolHandlerFactory  # noqa: E402
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.tools.parsers.gitleaks import (  # noqa: E402
    parse_gitleaks_json,
)
from tests.conftest import requires_gitleaks  # noqa: E402

pytestmark = pytest.mark.integration

_SECRET_CONTENT = "\n" * 9 + 'const aws_key = "AKIAZ3XYMWQ2LR7NVBPA";\n'
_TIMESTAMP = "2024-01-01T00:00:00"


def _make_secret_repo(path: Path) -> Path:
    """Create a minimal git repo with an AWS key at config/aws.js line 10."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@test.com"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "Test"],
        check=True,
        capture_output=True,
    )
    (path / "config").mkdir()
    (path / "config" / "aws.js").write_text(_SECRET_CONTENT)
    subprocess.run(
        ["git", "-C", str(path), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(path), "commit", "-m", "Add config"],
        check=True,
        capture_output=True,
    )
    return path


def _make_gitleaks_result(
    parsed_data: dict, output_files: dict | None = None
) -> ToolResult:
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data=parsed_data,
        output_files=output_files or {},
        timestamp=_TIMESTAMP,
        duration_seconds=0.1,
    )


@requires_gitleaks
class TestGitleaksBinaryRoundTrip:
    """Full chain: gitleaks binary to JSON to parser to normalize().

    These tests verify that field mappings are not broken end-to-end.
    They require ``gitleaks`` in PATH and are skipped otherwise.
    """

    def test_dir_scan_roundtrip(self, tmp_path: Path) -> None:
        """Dir-scan: every row field matches gitleaks output."""
        repo = _make_secret_repo(tmp_path / "git_repo")
        out = tmp_path / "findings.json"
        subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                ".",
                "--no-git",
                "--report-format",
                "json",
                "--report-path",
                str(out),
            ],
            capture_output=True,
            cwd=str(repo),
        )
        assert out.exists(), "gitleaks produced no output file; no findings detected"
        raw = json.loads(out.read_text())
        assert len(raw) > 0, "Expected at least one finding from the synthetic repo"

        parsed = parse_gitleaks_json(out)
        result = _make_gitleaks_result(parsed)
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        rows = handler.normalize(result, profile="roundtrip")

        assert len(rows) == len(raw), (
            f"Normalized {len(rows)} rows, gitleaks found {len(raw)} secrets"
        )
        row = rows[0]
        assert row["rule_id"] == raw[0]["RuleID"]
        assert row["file_path"] == raw[0]["File"]
        assert row["line_number"] == raw[0]["StartLine"]
        assert row["tool"] == "gitleaks"
        assert row["severity"] == "high"
        assert "commit" not in row, "Dir scan should have no commit key in row"

    def test_git_scan_roundtrip(self, tmp_path: Path) -> None:
        """Git-scan: commit hash from gitleaks is stored faithfully in row."""
        repo = _make_secret_repo(tmp_path / "git_repo")
        out = tmp_path / "findings.json"
        subprocess.run(
            [
                "gitleaks",
                "detect",
                "--source",
                ".",
                "--report-format",
                "json",
                "--report-path",
                str(out),
            ],
            capture_output=True,
            cwd=str(repo),
        )
        assert out.exists(), "gitleaks produced no output file"
        raw = json.loads(out.read_text())
        assert len(raw) > 0, "Expected at least one finding from the synthetic repo"
        assert raw[0]["Commit"], "git scan must produce a non-empty Commit hash"

        parsed = parse_gitleaks_json(out)
        result = _make_gitleaks_result(parsed)
        handler = ToolHandlerFactory.load("gitleaks")
        assert handler is not None
        rows = handler.normalize(result, profile="roundtrip-git")

        assert len(rows) == len(raw)
        row = rows[0]
        assert row["rule_id"] == raw[0]["RuleID"]
        assert row["file_path"] == raw[0]["File"]
        assert row["line_number"] == raw[0]["StartLine"]
        assert row["tool"] == "gitleaks"
        assert row["severity"] == "high"
        assert "commit" in row, "Git scan must store commit in row"
        assert row["commit"] == raw[0]["Commit"]
