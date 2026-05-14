"""Unit tests for post-scan sync hook."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from application.tools.scan_service import (
    _run_post_scan_sync,
    _sync_defectdojo,
)


def _mock_global_config(
    post_scan_sync: list[str] | None = None,
    dd_configured: bool = True,
) -> MagicMock:
    cfg = MagicMock()
    cfg.post_scan_sync = post_scan_sync or []
    if dd_configured:
        cfg.defectdojo = MagicMock()
        cfg.defectdojo.engagement_type = "Tally Engagement"
        cfg.defectdojo.product_type = "Tally Scan"
        cfg.defectdojo.auto_create_context = True
        cfg.defectdojo.scan_type = "Generic Findings Import"
        cfg.defectdojo.url = "http://dd.example.com"
        cfg.defectdojo.api_token = "token"
        cfg.defectdojo.verify_ssl = True
    else:
        cfg.defectdojo = None
    return cfg


def _mock_repo(id: int, name: str) -> MagicMock:
    repo = MagicMock()
    repo.id = id
    repo.name = name
    return repo


class TestRunPostScanSync:
    def test_noop_when_post_scan_sync_empty(self) -> None:
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        config_manager = MagicMock()
        global_config = _mock_global_config(post_scan_sync=[])
        config_manager.load_global_config.return_value = global_config

        with patch("core.config.manager.ConfigManager", return_value=config_manager):
            with patch("application.tools.scan_service._sync_defectdojo") as mock_sync:
                _run_post_scan_sync(
                    base_path="/test",
                    project_name="proj1",
                    run_id=1,
                    finding_repo=finding_repo,
                    repo_repo=repo_repo,
                    url_finding_repo=url_finding_repo,
                    tools_run=["semgrep"],
                    run_repo=run_repo,
                )

                mock_sync.assert_not_called()

    def test_calls_defectdojo_sync(self) -> None:
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        config_manager = MagicMock()
        global_config = _mock_global_config(post_scan_sync=["defectdojo"])
        config_manager.load_global_config.return_value = global_config

        with patch("core.config.manager.ConfigManager", return_value=config_manager):
            with patch("application.tools.scan_service._sync_defectdojo") as mock_sync:
                _run_post_scan_sync(
                    base_path="/test",
                    project_name="proj1",
                    run_id=1,
                    finding_repo=finding_repo,
                    repo_repo=repo_repo,
                    url_finding_repo=url_finding_repo,
                    tools_run=["semgrep"],
                    run_repo=run_repo,
                )

                mock_sync.assert_called_once_with(
                    config_manager,
                    global_config,
                    "proj1",
                    1,
                    finding_repo,
                    repo_repo,
                    url_finding_repo,
                    ["semgrep"],
                    run_repo,
                )

    def test_logs_warning_for_unknown_integration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        config_manager = MagicMock()
        global_config = _mock_global_config(post_scan_sync=["jira"])
        config_manager.load_global_config.return_value = global_config

        with patch("core.config.manager.ConfigManager", return_value=config_manager):
            with caplog.at_level(logging.WARNING):
                _run_post_scan_sync(
                    base_path="/test",
                    project_name="proj1",
                    run_id=1,
                    finding_repo=finding_repo,
                    repo_repo=repo_repo,
                    url_finding_repo=url_finding_repo,
                    tools_run=["semgrep"],
                    run_repo=run_repo,
                )

        assert "unknown integration 'jira'" in caplog.text

    def test_exceptions_propagate(self) -> None:
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        config_manager = MagicMock()
        config_manager.load_global_config.side_effect = RuntimeError("DB error")

        with patch("core.config.manager.ConfigManager", return_value=config_manager):
            with pytest.raises(RuntimeError, match="DB error"):
                _run_post_scan_sync(
                    base_path="/test",
                    project_name="proj1",
                    run_id=1,
                    finding_repo=finding_repo,
                    repo_repo=repo_repo,
                    url_finding_repo=url_finding_repo,
                    tools_run=["semgrep"],
                    run_repo=run_repo,
                )


class TestSyncDefectdojo:
    def test_exports_findings_for_run(self) -> None:
        config_manager = MagicMock()
        global_config = _mock_global_config(dd_configured=True)
        project_config = MagicMock()
        project_config.defectdojo = None
        config_manager.load_project_config.return_value = project_config

        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        repo_repo.list_active.return_value = [_mock_repo(1, "test-repo")]

        scan_row = MagicMock()
        scan_row.repo_ids = ["test-repo"]
        run_repo.get.return_value = scan_row

        export_result = MagicMock()
        export_result.success = True
        export_result.findings_exported = 5

        with patch(
            "infrastructure.export.defectdojo.adapter.DefectDojoExportAdapter"
        ) as mock_adapter:
            with patch("application.export.service.ExportService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.export.return_value = export_result

                _sync_defectdojo(
                    config_manager,
                    global_config,
                    "proj1",
                    1,
                    finding_repo,
                    repo_repo,
                    url_finding_repo,
                    ["semgrep"],
                    run_repo,
                )

                mock_adapter.assert_called_once()
                call_kwargs = mock_adapter.call_args[1]
                assert call_kwargs["config"] == global_config.defectdojo
                assert call_kwargs["project_name"] == "proj1"
                assert call_kwargs["engagement_type"] == "Tally Engagement"

                mock_service_instance.export.assert_called_once_with()
                assert mock_service.call_args.kwargs["run_id"] == 1

    def test_uses_project_engagement_override(self) -> None:
        config_manager = MagicMock()
        global_config = _mock_global_config(dd_configured=True)
        project_config = MagicMock()
        project_dd = MagicMock()
        project_dd.engagement_type = "CI/CD"
        project_config.defectdojo = project_dd
        config_manager.load_project_config.return_value = project_config

        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        repo_repo.list_active.return_value = [_mock_repo(1, "test-repo")]

        scan_row = MagicMock()
        scan_row.repo_ids = ["test-repo"]
        run_repo.get.return_value = scan_row

        export_result = MagicMock()
        export_result.success = True
        export_result.findings_exported = 3

        with patch(
            "infrastructure.export.defectdojo.adapter.DefectDojoExportAdapter"
        ) as mock_adapter:
            with patch("application.export.service.ExportService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.export.return_value = export_result

                _sync_defectdojo(
                    config_manager,
                    global_config,
                    "proj1",
                    1,
                    finding_repo,
                    repo_repo,
                    url_finding_repo,
                    ["semgrep"],
                    run_repo,
                )

                call_kwargs = mock_adapter.call_args[1]
                assert call_kwargs["engagement_type"] == "CI/CD"

    def test_skips_when_dd_not_configured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        config_manager = MagicMock()
        global_config = _mock_global_config(dd_configured=False)
        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()

        with caplog.at_level(logging.WARNING):
            _sync_defectdojo(
                config_manager,
                global_config,
                "proj1",
                1,
                finding_repo,
                repo_repo,
                url_finding_repo,
                ["semgrep"],
                run_repo,
            )

        assert "defectdojo listed in post_scan_sync but not configured" in (caplog.text)

    def test_logs_success(self, caplog: pytest.LogCaptureFixture) -> None:
        config_manager = MagicMock()
        global_config = _mock_global_config(dd_configured=True)
        project_config = MagicMock()
        project_config.defectdojo = None
        config_manager.load_project_config.return_value = project_config

        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        repo_repo.list_active.return_value = [_mock_repo(1, "test-repo")]

        scan_row = MagicMock()
        scan_row.repo_ids = ["test-repo"]
        run_repo.get.return_value = scan_row

        export_result = MagicMock()
        export_result.success = True
        export_result.findings_exported = 5

        with patch("infrastructure.export.defectdojo.adapter.DefectDojoExportAdapter"):
            with patch("application.export.service.ExportService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.export.return_value = export_result

                with caplog.at_level(logging.INFO):
                    _sync_defectdojo(
                        config_manager,
                        global_config,
                        "proj1",
                        1,
                        finding_repo,
                        repo_repo,
                        url_finding_repo,
                        ["semgrep"],
                        run_repo,
                    )

        assert "exported 5 findings to DefectDojo (run 1)" in caplog.text

    def test_logs_errors_on_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        config_manager = MagicMock()
        global_config = _mock_global_config(dd_configured=True)
        project_config = MagicMock()
        project_config.defectdojo = None
        config_manager.load_project_config.return_value = project_config

        finding_repo = MagicMock()
        repo_repo = MagicMock()
        url_finding_repo = MagicMock()
        run_repo = MagicMock()
        repo_repo.list_active.return_value = [_mock_repo(1, "test-repo")]

        scan_row = MagicMock()
        scan_row.repo_ids = ["test-repo"]
        run_repo.get.return_value = scan_row

        export_result = MagicMock()
        export_result.success = False
        export_result.findings_exported = 2
        export_result.findings_failed = 3
        export_result.errors = ("error 1", "error 2")

        with patch("infrastructure.export.defectdojo.adapter.DefectDojoExportAdapter"):
            with patch("application.export.service.ExportService") as mock_service:
                mock_service_instance = MagicMock()
                mock_service.return_value = mock_service_instance
                mock_service_instance.export.return_value = export_result

                with caplog.at_level(logging.WARNING):
                    _sync_defectdojo(
                        config_manager,
                        global_config,
                        "proj1",
                        1,
                        finding_repo,
                        repo_repo,
                        url_finding_repo,
                        ["semgrep"],
                        run_repo,
                    )

        assert "post-scan sync: error 1" in caplog.text
        assert "post-scan sync: error 2" in caplog.text
