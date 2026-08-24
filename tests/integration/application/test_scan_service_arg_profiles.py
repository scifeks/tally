"""Integration tests for ScanService arg profile snapshot handling."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from application.locking.registry import LockRegistry
from application.ports.subprocess_runner import SubprocessRunnerPort
from application.tools.scan_run_registry import ScanRunRegistry
from application.tools.scan_service import ScanService
from domain.tool_arg_profiles.entry import (
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.chat_sessions import (
    ChatSessionRepository,
)
from infrastructure.store.repositories.runs import RunRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def run_repo(factory: ConnectionFactory) -> RunRepository:
    return RunRepository(factory)


@pytest.fixture()
def chat_session_repo(factory: ConnectionFactory) -> ChatSessionRepository:
    return ChatSessionRepository(factory)


@pytest.fixture()
def profiles_repo(factory: ConnectionFactory) -> ToolArgProfilesRepository:
    return ToolArgProfilesRepository(factory)


@pytest.fixture()
def lock_registry() -> LockRegistry:
    return LockRegistry()


@pytest.fixture()
def scan_run_registry() -> ScanRunRegistry:
    return ScanRunRegistry()


@pytest.fixture()
def service(
    lock_registry: LockRegistry, scan_run_registry: ScanRunRegistry
) -> ScanService:
    svc = ScanService(
        subprocess_runner=MagicMock(spec=SubprocessRunnerPort),
        lock_registry=lock_registry,
        scan_run_registry=scan_run_registry,
    )
    svc._run_worker = MagicMock()  # type: ignore[method-assign]
    return svc


def _start_kwargs(
    run_repo: RunRepository,
    chat_session_repo: ChatSessionRepository,
    profiles_repo: ToolArgProfilesRepository,
    **overrides: object,
) -> Any:
    base: dict[str, object] = dict(
        project_id=1,
        project_name="test-proj",
        base_path="/tmp",
        tool_registry=MagicMock(list_tool_names=MagicMock(return_value=[])),
        run_repo=run_repo,
        chat_session_repo=chat_session_repo,
        profiles_repo=profiles_repo,
        finding_repo=MagicMock(),
        repo_repo=MagicMock(),
        url_finding_repo=MagicMock(),
        prompt=MagicMock(),
    )
    base.update(overrides)
    return base


class TestScanServiceArgProfiles:
    def test_start_scan_persists_saved_scan_id(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        with factory.connect() as conn:
            cur = conn.execute(
                "INSERT INTO saved_scans (name, skip_enrichment) VALUES (?, ?)",
                ("saved-scan-1", 0),
            )
            saved_scan_id = cur.lastrowid

        handle = service.start_scan(
            **_start_kwargs(
                run_repo,
                chat_session_repo,
                profiles_repo,
                saved_scan_id=saved_scan_id,
            )
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT saved_scan_id FROM scan_runs WHERE id = ?",
                (handle.run_id,),
            ).fetchone()

        assert row is not None
        assert row["saved_scan_id"] == saved_scan_id

    def test_start_scan_default_saved_scan_id_is_null(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        handle = service.start_scan(
            **_start_kwargs(run_repo, chat_session_repo, profiles_repo)
        )

        with factory.connect() as conn:
            row = conn.execute(
                "SELECT saved_scan_id FROM scan_runs WHERE id = ?",
                (handle.run_id,),
            ).fetchone()

        assert row is not None
        assert row["saved_scan_id"] is None

    def test_start_scan_validates_unknown_arg_profile_ids_raises(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        lock_registry: LockRegistry,
    ) -> None:
        with pytest.raises(ValueError):
            service.start_scan(
                **_start_kwargs(
                    run_repo,
                    chat_session_repo,
                    profiles_repo,
                    arg_profile_ids=[999],
                )
            )

        assert lock_registry.current_job_holder("scan") is None

        handle = service.start_scan(
            **_start_kwargs(run_repo, chat_session_repo, profiles_repo)
        )
        assert handle.run_id > 0

    def test_start_scan_persists_snapshots(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        p1 = profiles_repo.insert(
            tool_name="gitleaks",
            name="profile1",
            args=[ToolArgProfileFlagArg(name="-v")],
        )
        p2 = profiles_repo.insert(
            tool_name="semgrep",
            name="profile2",
            args=[ToolArgProfileStringArg(name="--config", value="cfg.yaml")],
        )

        handle = service.start_scan(
            **_start_kwargs(
                run_repo,
                chat_session_repo,
                profiles_repo,
                arg_profile_ids=[p1, p2],
            )
        )

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT tool, arg_profile_snapshot FROM run_tools"
                " WHERE run_id = ? ORDER BY tool",
                (handle.run_id,),
            ).fetchall()

        assert len(rows) == 2
        assert rows[0]["tool"] == "gitleaks"
        assert rows[0]["arg_profile_snapshot"] == json.dumps(
            [{"name": "-v", "type": "flag"}]
        )
        assert rows[1]["tool"] == "semgrep"
        assert rows[1]["arg_profile_snapshot"] == json.dumps(
            [
                {
                    "name": "--config",
                    "value": "cfg.yaml",
                    "operator": "",
                    "type": "string",
                }
            ]
        )

    def test_start_scan_snapshot_collision_later_wins(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        p1 = profiles_repo.insert(
            tool_name="gitleaks",
            name="first",
            args=[ToolArgProfileFlagArg(name="-v")],
        )
        p2 = profiles_repo.insert(
            tool_name="gitleaks",
            name="second",
            args=[ToolArgProfileStringArg(name="--config", value="cfg.yaml")],
        )

        handle = service.start_scan(
            **_start_kwargs(
                run_repo,
                chat_session_repo,
                profiles_repo,
                arg_profile_ids=[p1, p2],
            )
        )

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT tool, arg_profile_snapshot FROM run_tools WHERE run_id = ?",
                (handle.run_id,),
            ).fetchall()

        assert len(rows) == 1
        assert rows[0]["tool"] == "gitleaks"
        assert rows[0]["arg_profile_snapshot"] == json.dumps(
            [
                {
                    "name": "--config",
                    "value": "cfg.yaml",
                    "operator": "",
                    "type": "string",
                }
            ]
        )

    def test_start_scan_no_arg_profile_ids_writes_no_snapshot_rows(
        self,
        service: ScanService,
        run_repo: RunRepository,
        chat_session_repo: ChatSessionRepository,
        profiles_repo: ToolArgProfilesRepository,
        factory: ConnectionFactory,
    ) -> None:
        handle = service.start_scan(
            **_start_kwargs(run_repo, chat_session_repo, profiles_repo)
        )

        with factory.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM run_tools WHERE run_id = ?", (handle.run_id,)
            ).fetchall()

        assert len(rows) == 0
