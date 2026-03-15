"""Integration tests for search --show-fields and --fields flags.

Run from the tally project root::

    pytest tests/validation/test_search_integration.py -v

No external dependencies (no Ollama, no ChromaDB).
"""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console
from rich.table import Table

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from core.repl.commands.knowledge_commands import KnowledgeCommands  # noqa: E402
from core.store.sqlite_store import SQLiteStore  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROJECT_NAME = "test-proj"


def _make_store(tmp_path: Path) -> SQLiteStore:
    store = SQLiteStore(tmp_path, _PROJECT_NAME)
    return store


def _make_kc(store: SQLiteStore) -> tuple[MagicMock, KnowledgeCommands]:
    repl = MagicMock()
    repl.active_project = _PROJECT_NAME
    repl.console = MagicMock()
    kc = KnowledgeCommands(repl)
    kc._get_sqlite_store = MagicMock(return_value=store)
    return repl, kc


def _render(table: Table) -> str:
    buf = StringIO()
    con = Console(file=buf, markup=False, highlight=False, width=200)
    con.print(table)
    return buf.getvalue()


def _printed(repl: MagicMock) -> list[str]:
    return [str(c) for c in repl.console.print.call_args_list]


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_NMAP_WITH_META = [
    {
        "tool": "nmap",
        "domain": "network",
        "finding_type": "informational",
        "severity": "informational",
        "confidence": "confirmed",
        "ip_address": "10.0.0.1",
        "port": "22",
        "service": "ssh",
        "transport": "tcp",
    },
    {
        "tool": "nmap",
        "domain": "network",
        "finding_type": "informational",
        "severity": "high",
        "confidence": "confirmed",
        "ip_address": "10.0.0.2",
        "port": "443",
        # no service — to test N/A rendering
    },
]


def _seed_nmap(store: SQLiteStore) -> None:
    run_id = store.create_run({"args": []})
    store.upsert_findings(run_id, _NMAP_WITH_META)


# ---------------------------------------------------------------------------
# --show-fields tests
# ---------------------------------------------------------------------------


def test_show_fields_with_tool_and_findings(tmp_path: Path) -> None:
    """--show-fields --tool=nmap returns two labeled sections."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc._cmd_show_fields(["--show-fields", "--tool=nmap"])

    printed = _printed(repl)
    assert any("Schema fields" in p for p in printed)
    schema_line = next(p for p in printed if "Schema fields" in p)
    assert "severity" in schema_line
    assert "ip_address" in schema_line
    assert "fingerprint" in schema_line
    # service and transport go into meta blob
    assert any("Meta fields" in p for p in printed)
    meta_line = next(p for p in printed if "Meta fields" in p)
    assert "service" in meta_line


def test_show_fields_no_tool_prints_error(tmp_path: Path) -> None:
    """--show-fields without --tool prints an error."""
    store = _make_store(tmp_path)
    repl, kc = _make_kc(store)

    kc._cmd_show_fields(["--show-fields"])

    printed = _printed(repl)
    assert any("Error" in p for p in printed)


def test_show_fields_extra_flag_prints_error(tmp_path: Path) -> None:
    """--show-fields with extra flags prints an error."""
    store = _make_store(tmp_path)
    repl, kc = _make_kc(store)

    kc._cmd_show_fields(["--show-fields", "--tool=nmap", "--severity=high"])

    printed = _printed(repl)
    assert any("Error" in p for p in printed)


def test_show_fields_tool_with_no_findings(tmp_path: Path) -> None:
    """--show-fields for a tool with no findings prints appropriate message."""
    store = _make_store(tmp_path)
    repl, kc = _make_kc(store)

    kc._cmd_show_fields(["--show-fields", "--tool=zap"])

    printed = _printed(repl)
    assert any("No findings found" in p for p in printed)


# ---------------------------------------------------------------------------
# --fields tests
# ---------------------------------------------------------------------------


def _get_table(repl: MagicMock) -> Table | None:
    calls = repl.console.print.call_args_list
    for c in calls:
        if c[0] and isinstance(c[0][0], Table):
            return c[0][0]
    return None


def test_fields_basic_projection(tmp_path: Path) -> None:
    """--fields=severity,ip_address,service renders those columns."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc.cmd_search("search", ["--tool=nmap", "--fields=severity,ip_address,service"])

    table = _get_table(repl)
    assert table is not None, "expected a Rich Table to be printed"
    rendered = _render(table)
    assert "severity" in rendered
    assert "ip_address" in rendered
    assert "service" in rendered
    assert "informational" in rendered
    assert "10.0.0.1" in rendered
    assert "ssh" in rendered


def test_fields_na_for_missing_key(tmp_path: Path) -> None:
    """--fields renders N/A for a field absent from a row."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc.cmd_search("search", ["--tool=nmap", "--fields=severity,service"])

    table = _get_table(repl)
    assert table is not None
    rendered = _render(table)
    assert "N/A" in rendered


def test_fields_empty_value_prints_error(tmp_path: Path) -> None:
    """--fields= (empty value) prints a search error."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc.cmd_search("search", ["--fields="])

    printed = _printed(repl)
    assert any("Search error" in p or "error" in p.lower() for p in printed)


def test_fields_fingerprint_shows_sha256(tmp_path: Path) -> None:
    """--fields=fingerprint shows the computed SHA256, not N/A."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc.cmd_search("search", ["--tool=nmap", "--fields=fingerprint"])

    table = _get_table(repl)
    assert table is not None
    rendered = _render(table)
    assert "N/A" not in rendered
    assert len(rendered.strip()) > 0


def test_fields_no_tool_with_severity_filter(tmp_path: Path) -> None:
    """--severity=high --fields=severity,tool works without --tool."""
    store = _make_store(tmp_path)
    _seed_nmap(store)
    repl, kc = _make_kc(store)

    kc.cmd_search("search", ["--severity=high", "--fields=severity,tool"])

    table = _get_table(repl)
    assert table is not None, "expected a Rich Table to be printed"
    rendered = _render(table)
    assert "severity" in rendered
    assert "tool" in rendered
    assert "nmap" in rendered
