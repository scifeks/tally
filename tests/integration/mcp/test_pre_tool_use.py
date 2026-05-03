"""Tests for mcp.hooks.pre_tool_use."""

from __future__ import annotations

import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from tally_mcp.hooks.pre_tool_use import main  # noqa: E402

pytestmark = pytest.mark.integration

# Helpers

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tool_audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_name   TEXT    NOT NULL,
    arguments   TEXT,
    success     INTEGER NOT NULL DEFAULT 1,
    error       TEXT,
    duration_ms INTEGER,
    called_at   TEXT    NOT NULL
);
"""

_MCP_JSON_TEMPLATE = {
    "mcpServers": {
        "tally-mcp": {
            "command": "python3",
            "args": ["mcp/server.py", "--project", "hook-test"],
        }
    }
}


def _make_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _make_registry(tally_db: Path, name: str, project_path: Path) -> None:
    tally_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(tally_db))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            path        TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            ),
            archived_at TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO projects (name, path) VALUES (?, ?)",
        (name, str(project_path)),
    )
    conn.commit()
    conn.close()


def _row_count(db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM tool_audit_log").fetchone()[0]
    conn.close()
    return count


# Fixtures


@pytest.fixture()
def hook_env(tmp_path: Path) -> tuple[Path, Path]:
    db_path = tmp_path / "projects" / "hook-test" / "sqlite" / "findings.db"
    _make_db(db_path)
    mcp_json = tmp_path / ".mcp.json"
    mcp_json.write_text(json.dumps(_MCP_JSON_TEMPLATE))
    return tmp_path, db_path


# Tests


def test_normal_operation_writes_audit_row(
    monkeypatch: pytest.MonkeyPatch, hook_env: tuple[Path, Path]
) -> None:
    app_root, db_path = hook_env
    payload = json.dumps(
        {"tool_name": "Read", "tool_input": {"file_path": "/tmp/test.txt"}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    rc = main(app_root=app_root)

    assert rc == 0
    assert _row_count(db_path) == 1
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT tool_name, arguments, success FROM tool_audit_log"
    ).fetchone()
    conn.close()
    assert row[0] == "Read"
    assert json.loads(row[1]) == {"file_path": "/tmp/test.txt"}
    assert row[2] == 1


def test_registry_hit_writes_to_registered_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_path = tmp_path / "elsewhere" / "hook-test"
    db_path = project_path / "sqlite" / "findings.db"
    _make_db(db_path)
    _make_registry(tmp_path / "tally.db", "hook-test", project_path)
    (tmp_path / ".mcp.json").write_text(json.dumps(_MCP_JSON_TEMPLATE))

    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": "/tmp/x.txt"}}
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    rc = main(app_root=tmp_path)

    assert rc == 0
    assert _row_count(db_path) == 1
    canonical_db = tmp_path / "projects" / "hook-test" / "sqlite" / "findings.db"
    assert not canonical_db.exists()


def test_malformed_json_exits_zero(
    monkeypatch: pytest.MonkeyPatch, hook_env: tuple[Path, Path]
) -> None:
    app_root, db_path = hook_env
    monkeypatch.setattr(sys, "stdin", io.StringIO("bad json"))

    rc = main(app_root=app_root)

    assert rc == 0
    assert _row_count(db_path) == 0


def test_missing_mcp_json_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = json.dumps({"tool_name": "Read", "tool_input": {}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    rc = main(app_root=tmp_path)

    assert rc == 0


def test_malformed_mcp_json_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".mcp.json").write_text("not json at all")
    payload = json.dumps({"tool_name": "Read", "tool_input": {}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    rc = main(app_root=tmp_path)

    assert rc == 0


def test_missing_project_arg_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    mcp_json = {
        "mcpServers": {
            "tally-mcp": {
                "command": "python3",
                "args": ["mcp/server.py"],
            }
        }
    }
    (tmp_path / ".mcp.json").write_text(json.dumps(mcp_json))
    payload = json.dumps({"tool_name": "Read", "tool_input": {}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))

    rc = main(app_root=tmp_path)

    assert rc == 0
