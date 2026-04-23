"""Unit tests for ScanOrchestrator job-slot locking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from application.locking.exceptions import JobBusy
from application.locking.registry import LockRegistry
from application.tools.orchestrator import ScanOrchestrator


def _make_orchestrator(
    run_id: int | None,
    registry: LockRegistry,
) -> ScanOrchestrator:
    with patch("core.config.manager.ConfigManager"):
        return ScanOrchestrator(
            project="test-project",
            tool_registry=MagicMock(),
            tool_executor=MagicMock(base_path="/tmp"),
            event_bus=MagicMock(),
            prompt=MagicMock(),
            run_id=run_id,
            lock_registry=registry,
        )


class TestScanOrchestratorLock:
    def test_second_scan_while_slot_held_raises_job_busy(self) -> None:
        registry = LockRegistry()
        registry.acquire_job("scan", "scan-run:99")

        orchestrator = _make_orchestrator(run_id=100, registry=registry)

        with pytest.raises(JobBusy):
            orchestrator.run_full_scan()

    @patch("application.tools.orchestrator.FullScan")
    def test_no_run_id_skips_lock_acquisition(self, mock_full_scan: MagicMock) -> None:
        registry = LockRegistry()
        registry.acquire_job("scan", "scan-run:99")

        orchestrator = _make_orchestrator(run_id=None, registry=registry)

        orchestrator.run_full_scan()

        mock_full_scan.return_value.execute.assert_called_once()

    def test_run_segment_raises_job_busy_when_slot_held(self) -> None:
        registry = LockRegistry()
        registry.acquire_job("scan", "scan-run:99")

        orchestrator = _make_orchestrator(run_id=100, registry=registry)

        with pytest.raises(JobBusy):
            orchestrator.run_segment("sast")

    def test_run_repo_scan_raises_job_busy_when_slot_held(self) -> None:
        registry = LockRegistry()
        registry.acquire_job("scan", "scan-run:99")

        orchestrator = _make_orchestrator(run_id=100, registry=registry)

        with pytest.raises(JobBusy):
            orchestrator.run_repo_scan("my-repo")
