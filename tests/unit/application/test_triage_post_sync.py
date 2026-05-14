"""Unit tests for post-triage integration sync hook."""

from __future__ import annotations

from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from application.triage.triage_service import TriageService


def _build_service() -> TriageService:
    return TriageService(
        run_repo=MagicMock(),
        triage_repo=MagicMock(),
        finding_repo=MagicMock(),
        audit_repo=MagicMock(),
    )


def _make_global_config(
    post_triage_sync: list[str] | None = None,
) -> MagicMock:
    cfg = MagicMock()
    cfg.post_triage_sync = post_triage_sync or []
    return cfg


class TestTriagePostSync:
    def test_calls_sync_after_successful_triage(
        self,
    ) -> None:
        svc = _build_service()
        future: Future[dict[str, int]] = Future()

        gc = _make_global_config(post_triage_sync=["defectdojo"])

        with (
            patch(
                "application.triage.triage_service.run_triage_for_project",
                return_value={"success": 5},
            ),
            patch("application.triage.triage_service.ConfigManager") as mock_cm_cls,
            patch(
                "application.triage.triage_service.run_configured_syncs"
            ) as mock_sync,
        ):
            mock_cm_cls.return_value.load_global_config.return_value = gc

            svc._run_worker(
                future=future,
                holder_token="test",
                base_path="/app",
                project_id=1,
                project_name="proj",
                scan_run_id=42,
                event_sink=None,
                tool_registry=MagicMock(),
                cancel_token=MagicMock(),
                is_resume=False,
            )

            mock_sync.assert_called_once_with(
                base_path="/app",
                project_name="proj",
                run_id=42,
                sync_list=["defectdojo"],
            )

    def test_no_sync_when_post_triage_sync_empty(
        self,
    ) -> None:
        svc = _build_service()
        future: Future[dict[str, int]] = Future()

        gc = _make_global_config(post_triage_sync=[])

        with (
            patch(
                "application.triage.triage_service.run_triage_for_project",
                return_value={"success": 5},
            ),
            patch("application.triage.triage_service.ConfigManager") as mock_cm_cls,
            patch(
                "application.triage.triage_service.run_configured_syncs"
            ) as mock_sync,
        ):
            mock_cm_cls.return_value.load_global_config.return_value = gc

            svc._run_worker(
                future=future,
                holder_token="test",
                base_path="/app",
                project_id=1,
                project_name="proj",
                scan_run_id=42,
                event_sink=None,
                tool_registry=MagicMock(),
                cancel_token=MagicMock(),
                is_resume=False,
            )

            mock_sync.assert_called_once_with(
                base_path="/app",
                project_name="proj",
                run_id=42,
                sync_list=[],
            )

    def test_sync_failure_does_not_affect_result(
        self,
    ) -> None:
        svc = _build_service()
        future: Future[dict[str, int]] = Future()

        gc = _make_global_config(post_triage_sync=["defectdojo"])

        with (
            patch(
                "application.triage.triage_service.run_triage_for_project",
                return_value={"success": 5},
            ),
            patch("application.triage.triage_service.ConfigManager") as mock_cm_cls,
            patch(
                "application.triage.triage_service.run_configured_syncs",
                side_effect=RuntimeError("sync exploded"),
            ),
        ):
            mock_cm_cls.return_value.load_global_config.return_value = gc

            svc._run_worker(
                future=future,
                holder_token="test",
                base_path="/app",
                project_id=1,
                project_name="proj",
                scan_run_id=42,
                event_sink=None,
                tool_registry=MagicMock(),
                cancel_token=MagicMock(),
                is_resume=False,
            )

        assert future.result() == {"success": 5}
