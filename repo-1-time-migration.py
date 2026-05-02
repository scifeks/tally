"""One-time migration: backfill the new repositories table for projects/DVPA.

Reads the existing per-project SQLite ``repositories`` table (old shape:
id, uuid, name, created_at, deleted_at), reads the legacy
``projects/DVPA/config/project.json`` ``repositories: []`` array, drops
and recreates the table with the Phase 14.3 column shape, then INSERTs
each repo using the existing integer ``id`` so ``findings.repo_id`` /
``url_findings.repo_id`` references stay intact.

Soft-deleted rows that are absent from project.json are preserved with a
stub config + their original ``deleted_at`` stamp.

Throwaway. Delete after running once.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core.config.schemas.repository import RepoAuth, Repository  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    _repository_to_row,
)

PROJECT = "DVPA"
DB_PATH = ROOT / "projects" / PROJECT / "sqlite" / "findings.db"
JSON_PATH = ROOT / "projects" / PROJECT / "config" / "project.json"

NEW_CREATE = """
CREATE TABLE repositories (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    name                     TEXT NOT NULL,
    path                     TEXT NOT NULL DEFAULT '',
    docker_path              TEXT NOT NULL DEFAULT '',
    container_name           TEXT NOT NULL DEFAULT '',
    dependencies_file        TEXT NOT NULL DEFAULT '',
    crawl_enabled            INTEGER NOT NULL DEFAULT 1,
    xsstrike_crawl_level     INTEGER NOT NULL DEFAULT 10,
    katana_headless          INTEGER NOT NULL DEFAULT 0,
    katana_depth             INTEGER NOT NULL DEFAULT 5,
    type_json                TEXT NOT NULL DEFAULT '[]',
    languages_json           TEXT NOT NULL DEFAULT '[]',
    base_urls_json           TEXT NOT NULL DEFAULT '[]',
    test_dirs_json           TEXT NOT NULL DEFAULT '[]',
    ignore_dirs_json         TEXT NOT NULL DEFAULT '[]',
    xsstrike_headers_json    TEXT NOT NULL DEFAULT '{}',
    dalfox_headers_json      TEXT NOT NULL DEFAULT '{}',
    katana_headers_json      TEXT NOT NULL DEFAULT '{}',
    auth_json                TEXT,
    url_seed_file            TEXT,
    created_at               TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    ),
    deleted_at               TEXT
);
"""


def _build_repo(entry: dict) -> Repository:
    """Construct a Repository from a project.json entry; tolerate stale path."""
    auth_dict = entry.get("auth")
    auth = RepoAuth(**auth_dict) if auth_dict else None
    payload = {k: v for k, v in entry.items() if k not in ("uuid", "auth")}
    payload["auth"] = auth
    # path validator rejects non-existent paths; clear the path if it's gone so
    # we can still backfill the row. docker_path-only repos are unaffected.
    if payload.get("path") and not Path(payload["path"]).exists():
        print(
            f"  [warn] path missing on disk for {entry['name']}: "
            f"{payload['path']} — clearing"
        )
        payload["path"] = ""
    return Repository(**payload)


def main() -> int:
    if not DB_PATH.exists():
        print(f"FATAL: {DB_PATH} not found")
        return 1
    if not JSON_PATH.exists():
        print(f"FATAL: {JSON_PATH} not found")
        return 1

    project_json = json.loads(JSON_PATH.read_text())
    json_repos: list[dict] = project_json.get("repositories", [])
    json_by_name = {r["name"]: r for r in json_repos}

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        existing = list(
            conn.execute(
                "SELECT id, name, created_at, deleted_at FROM repositories ORDER BY id"
            ).fetchall()
        )
        existing_by_name = {r["name"]: r for r in existing}

        print(
            f"Found {len(existing)} existing rows; "
            f"{len(json_repos)} repos in project.json"
        )
        print()

        rebuilt: list[tuple[int, str, dict, str | None]] = []
        for r in existing:
            name = r["name"]
            entry = json_by_name.get(name)
            if entry is None:
                print(f"  [keep] id={r['id']} {name} (stub — not in project.json)")
                rebuilt.append((r["id"], name, {}, r["deleted_at"]))
                continue
            repo = _build_repo(entry)
            cols = _repository_to_row(repo)
            print(f"  [migrate] id={r['id']} {name}")
            rebuilt.append((r["id"], name, cols, r["deleted_at"]))

        # Catch repos that are in project.json but not in the DB — shouldn't
        # happen for DVPA but worth flagging.
        json_only = set(json_by_name) - set(existing_by_name)
        if json_only:
            print(f"  [warn] in JSON but not in DB (skipping): {sorted(json_only)}")

        print()
        print("Dropping and recreating repositories table...")
        conn.execute("DROP INDEX IF EXISTS idx_repositories_uuid")
        conn.execute("DROP INDEX IF EXISTS idx_repositories_deleted")
        conn.execute("DROP TABLE repositories")
        conn.executescript(NEW_CREATE)
        conn.execute(
            "CREATE INDEX idx_repositories_deleted ON repositories (deleted_at)"
        )

        for repo_id, name, cols, deleted_at in rebuilt:
            if not cols:
                # Stub row for a repo that was in the DB but not in project.json
                # (typically an already-soft-deleted entry the user trimmed
                # from the JSON). Insert just id + name + deleted_at.
                conn.execute(
                    "INSERT INTO repositories (id, name, deleted_at) VALUES (?, ?, ?)",
                    (repo_id, name, deleted_at),
                )
                continue
            cols_with_id = {"id": repo_id, **cols, "deleted_at": deleted_at}
            column_list = ", ".join(cols_with_id.keys())
            placeholders = ", ".join("?" for _ in cols_with_id)
            conn.execute(
                f"INSERT INTO repositories ({column_list}) VALUES ({placeholders})",
                tuple(cols_with_id.values()),
            )

        conn.commit()
        print()
        print("Verifying:")
        for r in conn.execute(
            "SELECT id, name, deleted_at, "
            "json_array_length(type_json) AS n_types, "
            "json_array_length(base_urls_json) AS n_urls "
            "FROM repositories ORDER BY id"
        ).fetchall():
            tag = "(deleted)" if r["deleted_at"] else ""
            print(
                f"  id={r['id']} name={r['name']:<12} "
                f"types={r['n_types']} urls={r['n_urls']} {tag}"
            )
    finally:
        conn.close()

    print()
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
