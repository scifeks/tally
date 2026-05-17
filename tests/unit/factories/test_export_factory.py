"""Unit tests for create_export_service_for_project."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from factories.export import create_export_service_for_project


class TestCreateExportServiceForProject:
    def test_builds_service_from_base_path(self) -> None:
        mock_factory = MagicMock()
        mock_conn = MagicMock()
        mock_factory.connect.return_value.__enter__ = lambda _: mock_conn
        mock_factory.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = []

        mock_repo_cls = MagicMock()
        mock_repo_instance = MagicMock()
        mock_repo_cls.return_value = mock_repo_instance
        mock_repo_instance.list_active.return_value = []

        mock_config_manager = MagicMock()
        mock_global_config = MagicMock()
        mock_global_config.defectdojo = MagicMock()
        mock_global_config.defectdojo.engagement_type = "Tally Engagement"
        mock_config_manager.load_global_config.return_value = mock_global_config
        mock_config_manager.load_project_config.return_value = None

        mock_paths = MagicMock()
        mock_paths.sqlite_dir = MagicMock()

        with (
            patch(
                "factories.export.ProjectPaths.from_canonical",
                return_value=mock_paths,
            ),
            patch(
                "factories.export.ConnectionFactory",
                return_value=mock_factory,
            ),
            patch(
                "factories.export.FindingRepository",
            ),
            patch(
                "factories.export.UrlFindingRepository",
            ),
            patch(
                "infrastructure.store.repositories.repositories.RepositoryRepository",
                mock_repo_cls,
            ),
            patch(
                "factories.export.ConfigManager",
                return_value=mock_config_manager,
            ),
            patch(
                "factories.export.build_export_service",
            ) as mock_build,
        ):
            create_export_service_for_project("/app", "myproject", run_id=42)

            mock_build.assert_called_once()
            kwargs = mock_build.call_args[1]
            assert kwargs["project_name"] == "myproject"
            assert kwargs["run_id"] == 42
            assert kwargs["engagement_type"] == "Tally Engagement"

    def test_raises_when_dd_not_configured(self) -> None:
        import pytest

        mock_config_manager = MagicMock()
        mock_global_config = MagicMock()
        mock_global_config.defectdojo = None
        mock_config_manager.load_global_config.return_value = mock_global_config

        mock_paths = MagicMock()
        mock_paths.sqlite_dir = MagicMock()

        with (
            patch(
                "factories.export.ProjectPaths.from_canonical",
                return_value=mock_paths,
            ),
            patch(
                "factories.export.ConfigManager",
                return_value=mock_config_manager,
            ),
            pytest.raises(Exception, match="not configured"),
        ):
            create_export_service_for_project("/app", "myproject", run_id=1)
