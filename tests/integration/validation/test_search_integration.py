"""Integration tests for search --show-fields and --fields flags.

No external dependencies (no Ollama, no ChromaDB).
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from rich.table import Table

from application.repl.commands.knowledge_commands import KnowledgeCommands
from infrastructure.store import make_store
from infrastructure.store.repositories.findings import FindingRepository
from infrastructure.store.repositories.runs import RunRepository

pytestmark = pytest.mark.integration

# Helpers

_PROJECT_NAME = "test-proj"


def _make_store(
    tmp_path: Path,
) -> tuple[RunRepository, FindingRepository]:
    run_repo, finding_repo, _, _ = make_store(tmp_path, _PROJECT_NAME)
    return run_repo, finding_repo


def _make_kc(
    finding_repo: FindingRepository,
) -> tuple[MagicMock, KnowledgeCommands]:
    repl = MagicMock()
    repl.active_project = _PROJECT_NAME
    repl.console = MagicMock()
    repl.tool_registry.list_tool_names.return_value = ["semgrep", "gitleaks", "zap"]
    kc = KnowledgeCommands(repl)
    kc._get_finding_repo = MagicMock(return_value=finding_repo)
    return repl, kc


def _render(table: Table) -> str:
    buf = StringIO()
    con = Console(file=buf, markup=False, highlight=False, width=200)
    con.print(table)
    return buf.getvalue()


def _printed(repl: MagicMock) -> list[str]:
    return [str(c) for c in repl.console.print.call_args_list]


# Seed data

_SEMGREP_WITH_META = [
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "informational",
        "confidence": "medium",
        "rule_id": "python.django.security.injection.sql-injection",
        "file_path": "src/api/users.py",
        "line_start": 42,
        "category": "security",  # goes into meta blob; used for N/A rendering test
        "cwe": "CWE-89",
    },
    {
        "tool": "semgrep",
        "domain": "code",
        "finding_type": "vulnerability",
        "severity": "high",
        "confidence": "high",
        "rule_id": "python.flask.security.audit.hardcoded-password",
        "file_path": "src/views/admin.py",
        "line_start": 15,
        # no category; row intentionally missing this field to test N/A rendering
    },
]


def _seed_semgrep(run_repo: RunRepository, finding_repo: FindingRepository) -> None:
    run_id = run_repo.create_run({"args": []})
    finding_repo.insert_findings(run_id, _SEMGREP_WITH_META)


# --show-fields tests


def test_show_fields_with_tool_and_findings(tmp_path: Path) -> None:
    """--show-fields --tool=semgrep returns two labeled sections."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc._cmd_show_fields(["--show-fields", "--tool=semgrep"])

    printed = _printed(repl)
    assert any("Schema fields" in p for p in printed)
    schema_line = next(p for p in printed if "Schema fields" in p)
    assert "rule_id" in schema_line
    assert "fingerprint" in schema_line
    assert "confidence" in schema_line
    # line_start and category go into meta blob
    assert any("Meta fields" in p for p in printed)
    meta_line = next(p for p in printed if "Meta fields" in p)
    assert "category" in meta_line


def test_show_fields_no_tool_prints_error(tmp_path: Path) -> None:
    """--show-fields without --tool prints an error."""
    _, finding_repo = _make_store(tmp_path)
    repl, kc = _make_kc(finding_repo)

    kc._cmd_show_fields(["--show-fields"])

    printed = _printed(repl)
    assert any("Error" in p for p in printed)


def test_show_fields_extra_flag_prints_error(tmp_path: Path) -> None:
    """--show-fields with extra flags prints an error."""
    _, finding_repo = _make_store(tmp_path)
    repl, kc = _make_kc(finding_repo)

    kc._cmd_show_fields(["--show-fields", "--tool=semgrep", "--severity=high"])

    printed = _printed(repl)
    assert any("Error" in p for p in printed)


def test_show_fields_tool_with_no_findings(tmp_path: Path) -> None:
    """--show-fields for a tool with no findings prints appropriate message."""
    _, finding_repo = _make_store(tmp_path)
    repl, kc = _make_kc(finding_repo)

    kc._cmd_show_fields(["--show-fields", "--tool=zap"])

    printed = _printed(repl)
    assert any("No findings found" in p for p in printed)


# --fields tests


def _get_table(repl: MagicMock) -> Table | None:
    calls = repl.console.print.call_args_list
    for c in calls:
        if c[0] and isinstance(c[0][0], Table):
            return c[0][0]
    return None


def test_fields_basic_projection(tmp_path: Path) -> None:
    """--fields=severity,rule_id,file_path renders those columns."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc.cmd_search("search", ["--tool=semgrep", "--fields=severity,rule_id,file_path"])

    table = _get_table(repl)
    assert table is not None, "expected a Rich Table to be printed"
    rendered = _render(table)
    assert "severity" in rendered
    assert "rule_id" in rendered
    assert "file_path" in rendered
    assert "informational" in rendered
    assert "src/api/users.py" in rendered
    assert "sql-injection" in rendered


def test_fields_na_for_missing_key(tmp_path: Path) -> None:
    """--fields renders N/A for a field absent from a row."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc.cmd_search("search", ["--tool=semgrep", "--fields=severity,category"])

    table = _get_table(repl)
    assert table is not None
    rendered = _render(table)
    assert "N/A" in rendered


def test_fields_empty_value_prints_error(tmp_path: Path) -> None:
    """--fields= (empty value) prints a search error."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc.cmd_search("search", ["--fields="])

    printed = _printed(repl)
    assert any("Search error" in p or "error" in p.lower() for p in printed)


def test_fields_fingerprint_shows_sha256(tmp_path: Path) -> None:
    """--fields=fingerprint shows the computed SHA256, not N/A."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc.cmd_search("search", ["--tool=semgrep", "--fields=fingerprint"])

    table = _get_table(repl)
    assert table is not None
    rendered = _render(table)
    assert "N/A" not in rendered
    assert len(rendered.strip()) > 0


def test_fields_no_tool_with_severity_filter(tmp_path: Path) -> None:
    """--severity=high --fields=severity,tool works without --tool."""
    run_repo, finding_repo = _make_store(tmp_path)
    _seed_semgrep(run_repo, finding_repo)
    repl, kc = _make_kc(finding_repo)

    kc.cmd_search("search", ["--severity=high", "--fields=severity,tool"])

    table = _get_table(repl)
    assert table is not None, "expected a Rich Table to be printed"
    rendered = _render(table)
    assert "severity" in rendered
    assert "tool" in rendered
    assert "semgrep" in rendered
