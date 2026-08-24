"""Unit tests for ScanService. The single core port for starting a scan.

The lock contract that previously lived in ScanOrchestrator now lives
here: ScanService.start_scan acquires the Tier-1 ``scan`` slot in the
calling thread (so JobBusy raises synchronously), creates the
scan_runs row, and dispatches a worker thread. These tests cover the
synchronous portion only; the worker is monkeypatched to a no-op so
the lock stays held and we can assert behavior cleanly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.locking.exceptions import JobBusy
from application.locking.registry import LockRegistry
from application.ports.subprocess_runner import SubprocessRunnerPort
from application.tools.scan_run_registry import ScanRunRegistry
from application.tools.scan_service import ScanService


@pytest.fixture
def registry() -> LockRegistry:
    return LockRegistry()


@pytest.fixture
def scan_run_registry() -> ScanRunRegistry:
    return ScanRunRegistry()


@pytest.fixture
def service(registry: LockRegistry, scan_run_registry: ScanRunRegistry) -> ScanService:
    svc = ScanService(
        subprocess_runner=MagicMock(spec=SubprocessRunnerPort),
        lock_registry=registry,
        scan_run_registry=scan_run_registry,
    )
    # Stub out the worker so the lock stays held and we don't run a real scan.
    svc._run_worker = MagicMock()  # type: ignore[method-assign]
    return svc


def _start_kwargs(
    *,
    run_repo: MagicMock | None = None,
    chat_session_repo: MagicMock | None = None,
    profiles_repo: MagicMock | None = None,
    finding_repo: MagicMock | None = None,
    repo_repo: MagicMock | None = None,
    url_finding_repo: MagicMock | None = None,
) -> dict:
    return dict(
        project_id=1,
        project_name="proj",
        base_path="/tmp",
        tool_registry=MagicMock(),
        run_repo=run_repo or MagicMock(),
        chat_session_repo=chat_session_repo or MagicMock(),
        profiles_repo=profiles_repo or MagicMock(),
        finding_repo=finding_repo or MagicMock(),
        repo_repo=repo_repo or MagicMock(),
        url_finding_repo=url_finding_repo or MagicMock(),
        prompt=MagicMock(),
    )


def test_start_scan_acquires_slot_and_returns_handle(
    service: ScanService, registry: LockRegistry
) -> None:
    run_repo = MagicMock()
    run_repo.create.return_value = 42
    handle = service.start_scan(**_start_kwargs(run_repo=run_repo))

    assert handle.run_id == 42
    assert registry.current_job_holder("scan") is not None


def test_second_start_raises_job_busy_synchronously(
    service: ScanService,
) -> None:
    run_repo = MagicMock()
    run_repo.create.return_value = 1
    service.start_scan(**_start_kwargs(run_repo=run_repo))

    with pytest.raises(JobBusy):
        service.start_scan(**_start_kwargs(run_repo=run_repo))


def test_lock_released_when_row_creation_fails(
    service: ScanService, registry: LockRegistry
) -> None:
    run_repo = MagicMock()
    run_repo.create.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        service.start_scan(**_start_kwargs(run_repo=run_repo))

    # Lock must have been released so a follow-up start can proceed.
    assert registry.current_job_holder("scan") is None


def test_cancel_token_registered_for_run(
    service: ScanService,
    scan_run_registry: ScanRunRegistry,
) -> None:
    run_repo = MagicMock()
    run_repo.create.return_value = 7
    handle = service.start_scan(**_start_kwargs(run_repo=run_repo))

    assert scan_run_registry.get(handle.run_id) is not None
