"""Integration tests for IngestHandler SQLite-first pipeline."""

from __future__ import annotations

import hashlib
import shutil
import struct
import sys
from pathlib import Path
from typing import Any

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[2]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.pipeline.handlers import IngestHandler  # noqa: E402
from application.ports.embedding_provider import EmbeddingProvider  # noqa: E402
from application.project import ProjectManager  # noqa: E402
from application.rag.knowledge_base import FindingKnowledgeBase  # noqa: E402
from core.project_paths import ProjectPaths  # noqa: E402
from domain.pipeline.events import (  # noqa: E402
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from domain.tools.base import ToolResult  # noqa: E402
from infrastructure.store import make_store  # noqa: E402
from infrastructure.tools.parsers.gitleaks import (  # noqa: E402
    parse_gitleaks_json,
)
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex  # noqa: E402

_DIM = 8


class _DeterministicEmbedding(EmbeddingProvider):
    def is_available(self) -> bool:
        return True

    def embed(self, text: str, **kwargs: Any) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return list(struct.unpack(f"<{_DIM}f", digest[: _DIM * 4]))


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
    pm.save_project(name)
    return {"base_path": tmp_path, "project_name": name}


@pytest.fixture()
def gitleaks_result() -> ToolResult:
    parsed = parse_gitleaks_json(_FIXTURES / "gitleaks_git.json")
    return ToolResult(
        tool_name="gitleaks",
        success=True,
        output="",
        parsed_data=parsed,
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


@pytest.fixture()
def zap_result() -> ToolResult:
    import json

    raw = json.loads((_FIXTURES / "zap_alerts.json").read_text())
    # The fixture is already in normalized format (alert_name, risk, etc.)
    return ToolResult(
        tool_name="zap",
        success=True,
        output="",
        parsed_data={"alerts": raw["alerts"], "summary": raw["summary"]},
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


class TestIngestHandlerPhase2:
    def test_sqlite_rows_written_after_tool_completed(
        self, project_env: dict, gitleaks_result: ToolResult
    ) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=gitleaks_result,
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
        assert len(findings) >= 1
        assert all(f.tool == "gitleaks" for f in findings)
        assert all(f.domain == "code" for f in findings)

    def test_chromadb_not_written_after_tool_completed(
        self, project_env: dict, gitleaks_result: ToolResult
    ) -> None:
        bus = EventBus()
        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=gitleaks_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)

        paths = ProjectPaths.from_canonical(
            project_env["base_path"], project_env["project_name"]
        )
        paths.chroma_db.mkdir(parents=True, exist_ok=True)
        chat_provider: Any = object()
        vector_index = ChromaDBVectorIndex(
            chroma_path=paths.chroma_db,
            collection_name=f"findings_{project_env['project_name']}",
            embedding_provider=_DeterministicEmbedding(),
        )
        kb = FindingKnowledgeBase(
            vector_index=vector_index,
            chat_provider=chat_provider,
            project_name=project_env["project_name"],
            base_path=project_env["base_path"],
        )
        try:
            assert kb.count() == 0
        finally:
            kb.close()

    def test_second_ingest_adds_new_rows(
        self, project_env: dict, gitleaks_result: ToolResult
    ) -> None:
        """Dispatching the same ToolCompleted twice produces separate rows.

        Scans are INSERT-only; each dispatch creates a new set of rows
        bound to its run_id.  No deduplication via fingerprint occurs.
        """
        bus = EventBus()
        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=gitleaks_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)
        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        count_after_first = len(finding_repo.get_all_findings())
        assert count_after_first >= 1

        handler.handle(event)
        count_after_second = len(finding_repo.get_all_findings())
        assert count_after_second == count_after_first * 2

    def test_ingest_completed_ids_are_sqlite_primary_keys(
        self, project_env: dict, gitleaks_result: ToolResult
    ) -> None:
        bus = EventBus()
        received: list[IngestCompleted] = []
        bus.subscribe(IngestCompleted, received.append)

        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=gitleaks_result,
            profile="test-profile",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
        )
        handler.handle(event)

        assert len(received) == 1
        ids = received[0].ids
        assert len(ids) >= 1
        assert all(isinstance(i, int) for i in ids)

        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        for finding_id in ids:
            row = finding_repo.get_finding(finding_id)
            assert row is not None
            assert row.tool == "gitleaks"

    def test_zap_findings_have_repo_populated(
        self, project_env: dict, zap_result: ToolResult
    ) -> None:
        """ZAP findings must have the repo column populated from event.repo."""
        bus = EventBus()
        handler = IngestHandler(bus)
        event = ToolCompleted(
            result=zap_result,
            profile="target-site",
            run_id=1,
            project_name=project_env["project_name"],
            base_path=str(project_env["base_path"]),
            repo="target-site",
        )
        handler.handle(event)

        _, finding_repo, _, _ = make_store(
            str(project_env["base_path"]), project_env["project_name"]
        )
        findings = finding_repo.get_all_findings_deserialized()
        assert len(findings) >= 1
        assert all(f["tool"] == "zap" for f in findings)
        assert all(f.get("repo") == "target-site" for f in findings), (
            f"Expected repo='target-site' on all ZAP findings, got: "
            f"{[f.get('repo') for f in findings]}"
        )
