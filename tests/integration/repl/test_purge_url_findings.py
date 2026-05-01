"""Verify REPL ``purge`` clears the ``url_findings`` table (Phase 9 Step 5).

Full-purge (no --tool) uses ``purge_non_preserved_tables``, which clears
all tables except those in ``ConnectionFactory.PRESERVED_TABLES``.
``url_findings`` is cleared; ``repositories`` rows survive.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[3]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.repl.commands.purge import PurgeCommand  # noqa: E402
from application.url_inventory.service import UrlInventoryService  # noqa: E402
from core.config.schemas.repository import Repository  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from domain.url_inventory.entry import UrlFinding, UrlSource  # noqa: E402
from infrastructure.store.connection import ConnectionFactory  # noqa: E402
from infrastructure.store.repositories.repositories import (  # noqa: E402
    RepositoryRepository,
)
from infrastructure.store.repositories.url_findings import (  # noqa: E402
    UrlFindingRepository,
)

pytestmark = pytest.mark.integration


MOCK_TOOLS = ["nmap", "semgrep"]


def _make_repl(tmp_path: Path) -> MagicMock:
    repl = MagicMock()
    repl.active_project = "testproj"
    repl.base_path = str(tmp_path)
    repl.console = MagicMock()
    return repl


def _seed_url_findings(tmp_path: Path) -> tuple[ConnectionFactory, int]:
    paths = ProjectPaths.from_canonical(tmp_path, "testproj")
    paths.sqlite_dir.mkdir(parents=True, exist_ok=True)
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    rr = RepositoryRepository(factory)
    rid = rr.insert(
        Repository(
            name="alpha",
            type=["api"],
            languages=["python"],
            docker_path="/app",
            container_name="ctr",
        )
    )
    UrlInventoryService(UrlFindingRepository(factory)).ingest_user_file(
        repo_id=rid,
        file_path="/uploads/spec.json",
        entries=[
            UrlFinding(
                repo_id=rid,
                source=UrlSource.USER,
                tool=None,
                run_id=None,
                method="GET",
                protocol="https",
                host="api.example.com",
                port=443,
                path="/api/x",
                file_path="/uploads/spec.json",
            )
        ],
    )
    return factory, rid


def _make_kb(doc_count: int = 5) -> MagicMock:
    kb = MagicMock()
    kb.count.return_value = doc_count
    kb.delete_findings.return_value = doc_count
    return kb


def test_full_purge_clears_url_findings(tmp_path: Path) -> None:
    factory, rid = _seed_url_findings(tmp_path)

    # Sanity: row exists pre-purge.
    pre = UrlFindingRepository(factory).list_for_repo(rid)
    assert len(pre) == 1

    cmd = PurgeCommand(_make_repl(tmp_path))
    with (
        patch.object(cmd, "_get_knowledge_base", return_value=_make_kb(0)),
        patch("application.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", [])

    # Post-purge: url_findings is empty; repositories row survives.
    paths = ProjectPaths.from_canonical(tmp_path, "testproj")
    fresh = ConnectionFactory(paths.findings_db)
    with fresh.connect() as conn:
        url_count = conn.execute("SELECT COUNT(*) FROM url_findings").fetchone()[0]
        repo_count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    assert url_count == 0
    assert repo_count == 1


def test_tool_purge_does_not_touch_url_findings(tmp_path: Path) -> None:
    """Tool-scoped purge leaves url_findings alone (it's not tool-scoped data)."""
    factory, rid = _seed_url_findings(tmp_path)

    cmd = PurgeCommand(_make_repl(tmp_path))
    with (
        patch.object(cmd, "_get_knowledge_base", return_value=_make_kb(2)),
        patch("application.repl.commands.purge.tool_registry") as mock_reg,
        patch("builtins.input", return_value="y"),
    ):
        mock_reg.list_tool_names.return_value = MOCK_TOOLS
        cmd.cmd_purge("purge", ["--tool=semgrep"])

    rows = UrlFindingRepository(factory).list_for_repo(rid)
    assert len(rows) == 1
