"""Unit tests for ``application.triage.triage_service.TriageService``."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from application.triage.factory import TriageProviderNotConfiguredError
from application.triage.triage_service import TriageService


class _StubRunRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "TriageService unit tests should not invoke RunRepositoryPort"
        )


class _StubTriageRepo:
    def __getattr__(self, _name: str) -> Any:
        raise AssertionError(
            "TriageService unit tests should not invoke TriageBatchRepositoryPort"
        )


class TestTriageService:
    def test_run_repo_property_exposes_constructed_handle(self) -> None:
        run_repo = _StubRunRepo()
        triage_repo = _StubTriageRepo()
        service = TriageService(
            run_repo=run_repo,  # type: ignore[arg-type]
            triage_repo=triage_repo,  # type: ignore[arg-type]
            finding_repo=MagicMock(),  # type: ignore[arg-type]
            audit_repo=MagicMock(),  # type: ignore[arg-type]
        )
        assert service.run_repo is run_repo

    def test_triage_repo_property_exposes_constructed_handle(self) -> None:
        run_repo = _StubRunRepo()
        triage_repo = _StubTriageRepo()
        service = TriageService(
            run_repo=run_repo,  # type: ignore[arg-type]
            triage_repo=triage_repo,  # type: ignore[arg-type]
            finding_repo=MagicMock(),  # type: ignore[arg-type]
            audit_repo=MagicMock(),  # type: ignore[arg-type]
        )
        assert service.triage_repo is triage_repo

    def test_start_triage_validates_provider_before_repo_access(
        self,
    ) -> None:
        run_repo = MagicMock()
        triage_repo = MagicMock()
        service = TriageService(
            run_repo=run_repo,
            triage_repo=triage_repo,
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
        )

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured",
            side_effect=TriageProviderNotConfiguredError("Triage is disabled."),
        ):
            with pytest.raises(TriageProviderNotConfiguredError, match="disabled"):
                service.start_triage(
                    base_path="/tmp/base",
                    project_id=1,
                    project_name="proj",
                    tool_registry=MagicMock(),
                )

        run_repo.latest_run_id.assert_not_called()

    def test_resume_triage_validates_provider_before_repo_access(
        self,
    ) -> None:
        run_repo = MagicMock()
        triage_repo = MagicMock()
        service = TriageService(
            run_repo=run_repo,
            triage_repo=triage_repo,
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
        )

        with patch(
            "application.triage.triage_service.ensure_triage_backend_configured",
            side_effect=TriageProviderNotConfiguredError("Triage is disabled."),
        ):
            with pytest.raises(TriageProviderNotConfiguredError, match="disabled"):
                service.resume_triage(
                    base_path="/tmp/base",
                    project_id=1,
                    project_name="proj",
                    scan_run_id=9,
                    tool_registry=MagicMock(),
                )

        triage_repo.summarize_for_run.assert_not_called()

    def test_run_worker_ensures_containers_before_orchestrator(
        self,
    ) -> None:
        """_run_worker must start containers before calling the orchestrator."""
        from concurrent.futures import Future

        from application.locking.cancellation import no_op_token

        lock_reg = MagicMock()
        run_reg = MagicMock()
        service = TriageService(
            run_repo=MagicMock(),
            triage_repo=MagicMock(),
            finding_repo=MagicMock(),
            audit_repo=MagicMock(),
            lock_registry=lock_reg,
            triage_run_registry=run_reg,
        )

        call_order: list[str] = []

        def _track(name: str):
            def _side_effect(*_a, **_kw):
                call_order.append(name)
                if name == "orchestrator":
                    return {"success": 5, "failed": 0}
                return None

            return _side_effect

        future: Future[dict[str, int]] = Future()

        with (
            patch(
                "application.triage.container.ensure_triage_image",
                side_effect=_track("image"),
            ),
            patch(
                "application.triage.container.ensure_triage_containers",
                side_effect=_track("containers"),
            ),
            patch(
                "application.triage.triage_service.run_triage_for_project",
                side_effect=_track("orchestrator"),
            ),
            patch(
                "application.triage.container.teardown_triage_containers",
            ),
            patch(
                "application.triage.triage_service.run_configured_syncs",
            ),
        ):
            service._run_worker(
                future=future,
                holder_token="tok",
                base_path="/tmp/triage-test",
                project_id=1,
                project_name="proj",
                scan_run_id=1,
                event_sink=None,
                tool_registry=MagicMock(),
                cancel_token=no_op_token(),
                is_resume=False,
            )

        assert call_order == [
            "image",
            "containers",
            "orchestrator",
        ]
