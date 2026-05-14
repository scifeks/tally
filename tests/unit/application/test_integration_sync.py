"""Unit tests for shared integration sync module."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from application.sync.integration_sync import (
    run_configured_syncs,
)


class TestRunConfiguredSyncs:
    def test_noop_when_sync_list_empty(self) -> None:
        with patch("application.sync.integration_sync._sync_defectdojo") as mock_sync:
            run_configured_syncs(
                base_path="/test",
                project_name="proj1",
                run_id=1,
                sync_list=[],
            )
            mock_sync.assert_not_called()

    def test_calls_defectdojo_sync(self) -> None:
        with patch("application.sync.integration_sync._sync_defectdojo") as mock_sync:
            run_configured_syncs(
                base_path="/test",
                project_name="proj1",
                run_id=1,
                sync_list=["defectdojo"],
            )
            mock_sync.assert_called_once_with("/test", "proj1", 1)

    def test_logs_warning_for_unknown_integration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            run_configured_syncs(
                base_path="/test",
                project_name="proj1",
                run_id=1,
                sync_list=["jira"],
            )
        assert "unknown integration 'jira'" in caplog.text

    def test_exception_in_sync_is_logged_not_raised(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with patch(
            "application.sync.integration_sync._sync_defectdojo",
            side_effect=RuntimeError("connection refused"),
        ):
            with caplog.at_level(logging.ERROR):
                run_configured_syncs(
                    base_path="/test",
                    project_name="proj1",
                    run_id=1,
                    sync_list=["defectdojo"],
                )
            assert "defectdojo sync failed" in caplog.text

    def test_continues_after_one_integration_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        call_order: list[str] = []

        def fake_dd_sync(*_args: object) -> None:
            call_order.append("defectdojo")
            raise RuntimeError("fail")

        with (
            patch(
                "application.sync.integration_sync._sync_defectdojo",
                side_effect=fake_dd_sync,
            ),
            caplog.at_level(logging.WARNING),
        ):
            run_configured_syncs(
                base_path="/test",
                project_name="proj1",
                run_id=1,
                sync_list=["defectdojo", "jira"],
            )
        assert "defectdojo" in call_order
        assert "unknown integration 'jira'" in caplog.text


class TestSyncDefectdojo:
    def test_calls_factory_and_exports(self) -> None:
        from application.sync.integration_sync import (
            _sync_defectdojo,
        )

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.findings_exported = 5
        mock_service.export.return_value = mock_result

        with patch(
            "factories.export.create_export_service_for_project",
            return_value=mock_service,
        ) as mock_factory:
            _sync_defectdojo("/test", "proj1", 42)

            mock_factory.assert_called_once_with(
                base_path="/test",
                project_name="proj1",
                run_id=42,
            )
            mock_service.export.assert_called_once()

    def test_logs_success(self, caplog: pytest.LogCaptureFixture) -> None:
        from application.sync.integration_sync import (
            _sync_defectdojo,
        )

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.findings_exported = 5
        mock_service.export.return_value = mock_result

        with (
            patch(
                "factories.export.create_export_service_for_project",
                return_value=mock_service,
            ),
            caplog.at_level(logging.INFO),
        ):
            _sync_defectdojo("/test", "proj1", 42)

        assert "exported 5 findings to DefectDojo (run 42)" in caplog.text

    def test_logs_errors_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        from application.sync.integration_sync import (
            _sync_defectdojo,
        )

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ("error 1", "error 2")
        mock_service.export.return_value = mock_result

        with (
            patch(
                "factories.export.create_export_service_for_project",
                return_value=mock_service,
            ),
            caplog.at_level(logging.WARNING),
        ):
            _sync_defectdojo("/test", "proj1", 1)

        assert "integration sync: error 1" in caplog.text
        assert "integration sync: error 2" in caplog.text

    def test_raises_when_dd_not_configured(self) -> None:
        from application.sync.integration_sync import (
            _sync_defectdojo,
        )
        from factories.export import ExportNotConfigured

        with (
            patch(
                "factories.export.create_export_service_for_project",
                side_effect=ExportNotConfigured("not configured"),
            ),
            pytest.raises(ExportNotConfigured),
        ):
            _sync_defectdojo("/test", "proj1", 1)
