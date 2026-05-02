"""Unit tests for ScanService. The single core port for starting a scan.

The lock contract that previously lived in ScanOrchestrator now lives
here: ScanService.start_scan acquires the Tier-1 ``scan`` slot in the
calling thread (so JobBusy raises synchronously), creates the
scan_runs row, and dispatches a worker thread. These tests cover the
synchronous portion only; the worker is monkeypatched to a no-op so
the lock stays held and we can assert behaviour cleanly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from application.locking.exceptions import JobBusy
from application.locking.registry import LockRegistry
from application.tools.scan_run_registry import ScanRunRegistry
from application.tools.scan_service import ScanService
from core.project_paths import ProjectPaths


@pytest.fixture
def registry() -> LockRegistry:
    return LockRegistry()


@pytest.fixture
def scan_run_registry() -> ScanRunRegistry:
    return ScanRunRegistry()


@pytest.fixture
def service(registry: LockRegistry, scan_run_registry: ScanRunRegistry) -> ScanService:
    svc = ScanService(lock_registry=registry, scan_run_registry=scan_run_registry)
    # Stub out the worker so the lock stays held and we don't run a real scan.
    svc._run_worker = MagicMock()  # type: ignore[method-assign]
    return svc


def _start_kwargs(paths: ProjectPaths) -> dict:
    return dict(
        project_id=1,
        project_name="proj",
        base_path="/tmp",
        paths=paths,
        prompt=MagicMock(),
    )


def test_start_scan_acquires_slot_and_returns_handle(
    service: ScanService, registry: LockRegistry, tmp_path: Path
) -> None:
    paths = ProjectPaths(tmp_path)
    paths.sqlite_dir.mkdir()
    with patch("application.tools.scan_service.RunRepository") as run_repo_cls:
        run_repo_cls.return_value.create.return_value = 42
        handle = service.start_scan(**_start_kwargs(paths))

    assert handle.run_id == 42
    assert registry.current_job_holder("scan") is not None


def test_second_start_raises_job_busy_synchronously(
    service: ScanService, registry: LockRegistry, tmp_path: Path
) -> None:
    paths = ProjectPaths(tmp_path)
    paths.sqlite_dir.mkdir()
    with patch("application.tools.scan_service.RunRepository") as run_repo_cls:
        run_repo_cls.return_value.create.return_value = 1
        service.start_scan(**_start_kwargs(paths))

        with pytest.raises(JobBusy):
            service.start_scan(**_start_kwargs(paths))


def test_lock_released_when_row_creation_fails(
    service: ScanService, registry: LockRegistry, tmp_path: Path
) -> None:
    paths = ProjectPaths(tmp_path)
    paths.sqlite_dir.mkdir()
    with patch("application.tools.scan_service.RunRepository") as run_repo_cls:
        run_repo_cls.return_value.create.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            service.start_scan(**_start_kwargs(paths))

    # Lock must have been released so a follow-up start can proceed.
    assert registry.current_job_holder("scan") is None


def test_cancel_token_registered_for_run(
    service: ScanService,
    scan_run_registry: ScanRunRegistry,
    tmp_path: Path,
) -> None:
    paths = ProjectPaths(tmp_path)
    paths.sqlite_dir.mkdir()
    with patch("application.tools.scan_service.RunRepository") as run_repo_cls:
        run_repo_cls.return_value.create.return_value = 7
        handle = service.start_scan(**_start_kwargs(paths))

    assert scan_run_registry.get(handle.run_id) is not None
