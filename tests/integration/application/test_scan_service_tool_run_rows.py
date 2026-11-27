"""Tests that a real ScanService run writes one run_tools row per service."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from application.locking.registry import LockRegistry
from application.ports.tool_runner import CliToolRunnerPort
from application.tools.scan_run_registry import ScanRunRegistry
from application.tools.scan_service import ScanService
from core.config.schemas.repository import RepoService, Repository
from domain.tools.base import ToolResult
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_sessions import (
    ChatSessionRepository,
)
from infrastructure.store.repositories.repositories import (
    RepositoryRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration

TOOL = "fake-tool"


def _seed_global_config(base_path: Path) -> None:
    config_dir = base_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "global.json").write_text(
        json.dumps(
            {
                "ollama": {
                    "model": "test-model",
                    "base_url": "http://localhost:11434",
                },
                "embedding_inference": {
                    "provider": "ollama",
                    "model": "test-embed",
                },
            }
        )
    )


def _service(name: str) -> RepoService:
    return RepoService(name=name, type=["api"], languages=["python"])


def _tool_registry() -> MagicMock:
    registered = SimpleNamespace(
        name=TOOL,
        always_run=True,
        language_gates=[],
        scan_segment="sast",
        is_discovery_tool=False,
    )
    registry = MagicMock()
    registry.list_tool_names.return_value = [TOOL]
    registry.get_all_tools.return_value = [registered]
    registry.get_tool.return_value = registered
    registry.resolve_tool_config.return_value = MagicMock(location="local")
    return registry


def _fake_tool() -> MagicMock:
    tool = MagicMock(requires_base_urls=False, findings_exit_ok=False)
    tool.check_available.return_value = True
    tool.count_findings.return_value = 0
    return tool


def _success() -> ToolResult:
    return ToolResult(
        tool_name=TOOL,
        success=True,
        output="",
        parsed_data={},
        output_files={},
        timestamp=ToolResult.now_iso(),
        duration_seconds=0.1,
    )


class TestScanServiceToolRunRows:
    def test_scan_writes_one_done_row_per_service_and_no_summed_row(
        self, tmp_path: Path
    ) -> None:
        _seed_global_config(tmp_path)
        factory = ConnectionFactory(tmp_path / "findings.db")
        factory.init_schema()
        repo_repo = RepositoryRepository(factory)
        repo_id = repo_repo.insert(
            Repository(
                name="shop",
                path=str(tmp_path / "shop"),
                services=[_service("api"), _service("ui")],
            )
        )
        runs = RunRepository(factory)
        service = ScanService(
            cli_tool_runner=MagicMock(spec=CliToolRunnerPort),
            lock_registry=LockRegistry(),
            scan_run_registry=ScanRunRegistry(),
        )
        wrapper_factory = MagicMock()
        wrapper_factory.create.return_value = _fake_tool()

        with (
            patch(
                "application.tools.scan_service.ToolWrapperFactory",
                return_value=wrapper_factory,
            ),
            patch(
                "application.tools.scan_types.repo.execute_tool_passes",
                side_effect=lambda *a, **k: _success(),
            ),
        ):
            handle = service.start_scan(
                project_id=1,
                project_name="test-proj",
                base_path=str(tmp_path),
                tool_registry=_tool_registry(),
                run_repo=runs,
                chat_session_repo=ChatSessionRepository(factory),
                profiles_repo=ToolArgProfilesRepository(factory),
                finding_repo=MagicMock(),
                repo_repo=repo_repo,
                url_finding_repo=MagicMock(),
                repo_ids=("shop",),
                skip_enrichment=True,
                prompt=MagicMock(),
            )
            handle.result.result(timeout=30)

        bundle = runs.get_with_tool_runs(handle.run_id)
        assert bundle is not None
        rows = sorted((r.tool, r.repo_id, r.service, r.status) for r in bundle[1])
        assert rows == [
            (TOOL, repo_id, "api", "done"),
            (TOOL, repo_id, "ui", "done"),
        ]
