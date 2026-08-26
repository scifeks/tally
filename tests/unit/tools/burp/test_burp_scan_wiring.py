"""Verify Burp wiring: registration in discover_tools and
ScanService routing to run_burp_scan."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from application.tools.registry import ToolRegistry, discover_tools
from application.tools.scan_service import ScanService
from domain.tools.scan_types import ScanSummary


class TestBurpRegistrationInDiscoverTools:
    def test_registers_burp_when_configured_and_available(self, tmp_path):
        registry = ToolRegistry()
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "commands.json").write_text("{}")

        with patch("application.tools.registry.register_burp_tool") as mock_register:
            discover_tools(registry, str(tmp_path))

        mock_register.assert_called_once_with(registry, str(tmp_path))

    def test_discover_tools_survives_register_burp_failure(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "commands.json").write_text("{}")
        registry = ToolRegistry()

        with patch(
            "application.tools.registry.register_burp_tool",
            side_effect=Exception("boom"),
        ):
            discover_tools(registry, str(tmp_path))


class TestScanServiceBurpRouting:
    def test_start_scan_with_burp_urls_calls_run_burp_scan(self):
        cli_runner = MagicMock()
        service = ScanService(cli_tool_runner=cli_runner)

        mock_orchestrator = MagicMock()
        mock_orchestrator.run_burp_scan.return_value = ScanSummary(
            total_tools_run=1,
            total_tools_skipped=0,
            total_tools_failed=0,
            results=[],
            duration_seconds=1.0,
            findings_ingested=0,
            findings_by_tool={},
        )

        with (
            patch.object(service, "_lock_registry"),
            patch.object(service, "_scan_run_registry"),
            patch(
                "application.tools.scan_service.ScanOrchestrator",
                return_value=mock_orchestrator,
            ),
            patch(
                "application.tools.scan_service.ToolExecutor",
            ),
            patch(
                "application.pipeline.factory.PipelineFactory",
            ) as mock_pf,
            patch(
                "factories.scanning.reset_scan_scoped_state",
            ),
            patch(
                "core.config.manager.ConfigManager",
            ) as mock_cfg_mgr,
            patch(
                "infrastructure.tools.burp.rest_client.BurpRestClient",
            ),
            patch(
                "infrastructure.tools.http_runner.HttpToolRunner",
            ),
        ):
            mock_pf.create.return_value = MagicMock()
            mock_burp_config = MagicMock()
            mock_burp_config.base_url = "http://localhost:1337"
            mock_burp_config.api_key = "test-key"
            mock_cfg = MagicMock()
            mock_cfg.global_config.burp = mock_burp_config
            mock_cfg_mgr.return_value = mock_cfg
            run_repo = MagicMock()
            run_repo.create.return_value = 1

            handle = service.start_scan(
                project_id=1,
                project_name="test",
                base_path="/tmp/test",
                tool_registry=ToolRegistry(),
                run_repo=run_repo,
                chat_session_repo=MagicMock(),
                profiles_repo=MagicMock(),
                finding_repo=MagicMock(),
                repo_repo=MagicMock(),
                url_finding_repo=MagicMock(),
                prompt=MagicMock(),
                burp_urls=["https://target.example.com"],
                burp_config_name="test-config",
                burp_timeout=300,
            )
            handle.result.result(timeout=5)

        mock_orchestrator.run_burp_scan.assert_called_once()
        call_kwargs = mock_orchestrator.run_burp_scan.call_args.kwargs
        assert call_kwargs["urls"] == ["https://target.example.com"]
        assert call_kwargs["config_name"] == "test-config"
        assert call_kwargs["timeout"] == 300
