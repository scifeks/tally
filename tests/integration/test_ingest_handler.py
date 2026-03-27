"""Integration tests for IngestHandler — Phase 2 SQLite-first pipeline."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import chromadb.utils.embedding_functions as ef
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.pipeline.handlers import IngestHandler  # noqa: E402
from application.project import ProjectManager  # noqa: E402
from application.rag.engine import RAGEngine  # noqa: E402
from domain.pipeline.events import (  # noqa: E402
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.tools.parsers.nmap_parser import parse_nmap_xml  # noqa: E402

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "ingest"


def _write_global_config(base_path: Path) -> None:
    real_config = _TALLY_ROOT / "config" / "global.json"
    if not real_config.exists():
        pytest.skip("config/global.json not found")
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(real_config, config_dir / "global.json")


@pytest.fixture()
def project_env(tmp_path: Path) -> dict:
    name = "test-proj"
    _write_global_config(tmp_path)
    pm = ProjectManager(base_path=str(tmp_path))
    pm.create_project_dirs(name)
    pm.save_project(name, [])
    return {"base_path": tmp_path, "project_name": name}


@pytest.fixture()
def nmap_result() -> ToolResult:
    parsed = parse_nmap_xml(_FIXTURES / "nmap_basic.xml")
    return ToolResult(
        tool_name="nmap",
        success=True,
        output="",
        parsed_data=parsed,
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


class TestIngestHandlerPhase2:
    def test_sqlite_rows_written_after_tool_completed(
        self, project_env: dict, nmap_result: ToolResult
    ) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=nmap_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)

        assert len(received) == 1
        assert len(received[0].ids) > 0
        assert received[0].failed_tools == []

        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        findings = finding_repo.get_all_findings()
        # nmap_basic.xml has 2 open ports (80, 443)
        assert len(findings) == 2
        assert all(f["tool"] == "nmap" for f in findings)
        assert all(f["domain"] == "network" for f in findings)
        ports = {f["port"] for f in findings}
        assert ports == {"80", "443"}

    def test_chromadb_not_written_after_tool_completed(
        self, project_env: dict, nmap_result: ToolResult
    ) -> None:
        bus = EventBus()
        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=nmap_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)

        default_fn = ef.DefaultEmbeddingFunction()
        with patch.object(
            RAGEngine, "_build_embedding_function", return_value=default_fn
        ):
            engine = RAGEngine(
                project_name=project_env["project_name"],
                base_path=str(project_env["base_path"]),
            )
        assert engine.count_documents() == 0

    def test_sqlite_deduplicates_on_second_ingest(
        self, project_env: dict, nmap_result: ToolResult
    ) -> None:
        """Dispatching the same ToolCompleted twice must not add new rows.

        The ON CONFLICT (fingerprint) clause in upsert_findings() must
        increment seen_count instead of inserting duplicates.
        """
        bus = EventBus()
        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=nmap_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)
        handler.handle(event)

        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        findings = finding_repo.get_all_findings()
        assert len(findings) == 2  # still only 2 rows (port 80 and 443)
        for finding in findings:
            assert finding["seen_count"] == 2

    def test_ingest_completed_ids_are_sqlite_primary_keys(
        self, project_env: dict, nmap_result: ToolResult
    ) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=nmap_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)

        assert len(received) == 1
        ids = received[0].ids
        assert len(ids) == 2
        assert all(isinstance(i, int) for i in ids)

        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        for finding_id in ids:
            row = finding_repo.get_finding(finding_id)
            assert row is not None
            assert row["tool"] == "nmap"
