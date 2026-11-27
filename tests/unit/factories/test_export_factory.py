"""Unit tests for the names the export factory resolves."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from factories.export import (
    ExportNotConfigured,
    create_export_service_for_project,
)


def _build_kwargs(
    *,
    company_name: str,
    project_engagement: str | None,
    override: str | None,
) -> dict:
    global_config = MagicMock()
    global_config.defectdojo.engagement_name = "Global Engagement"
    project_config = SimpleNamespace(
        company_name=company_name,
        defectdojo=SimpleNamespace(engagement_name=project_engagement),
    )
    config_manager = MagicMock()
    config_manager.load_global_config.return_value = global_config
    config_manager.load_project_config.return_value = project_config
    repo_repo = MagicMock()
    repo_repo.list_active.return_value = []

    with (
        patch("factories.export.ProjectPaths.from_canonical"),
        patch("factories.export.ConnectionFactory"),
        patch("factories.export.FindingRepository"),
        patch("factories.export.UrlFindingRepository"),
        patch("factories.export.RunRepository"),
        patch("factories.export.RepositoryRepository", return_value=repo_repo),
        patch("factories.export.ConfigManager", return_value=config_manager),
        patch("factories.export.build_export_service") as build,
    ):
        create_export_service_for_project(
            "/app", "myapp", run_id=42, engagement_name_override=override
        )
    return dict(build.call_args.kwargs)


class TestExportFactoryNames:
    @pytest.mark.parametrize(
        ("company_name", "expected"),
        [("Acme Corp", "Acme Corp"), ("", "myapp")],
        ids=["company_name", "falls_back_to_project_name"],
    )
    def test_organization_name(self, company_name: str, expected: str) -> None:
        kwargs = _build_kwargs(
            company_name=company_name, project_engagement=None, override=None
        )

        assert kwargs["organization_name"] == expected
        assert kwargs["project_name"] == "myapp"
        assert kwargs["run_id"] == 42

    @pytest.mark.parametrize(
        ("project_engagement", "override", "expected"),
        [
            (None, None, "Global Engagement"),
            ("Project Engagement", None, "Project Engagement"),
            ("Project Engagement", "Flag Engagement", "Flag Engagement"),
        ],
        ids=["global", "project_over_global", "flag_over_project"],
    )
    def test_engagement_name_precedence(
        self, project_engagement: str | None, override: str | None, expected: str
    ) -> None:
        kwargs = _build_kwargs(
            company_name="Acme Corp",
            project_engagement=project_engagement,
            override=override,
        )

        assert kwargs["engagement_name"] == expected

    def test_raises_when_defectdojo_is_not_configured(self) -> None:
        config_manager = MagicMock()
        config_manager.load_global_config.return_value.defectdojo = None

        with (
            patch("factories.export.ProjectPaths.from_canonical"),
            patch("factories.export.ConfigManager", return_value=config_manager),
            pytest.raises(ExportNotConfigured, match="not configured"),
        ):
            create_export_service_for_project("/app", "myapp")
