"""Unit tests for project resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.cli.project import ProjectResolutionError, resolve_project
from domain.projects.entry import ProjectRow


class TestResolveProject:
    def test_returns_project_id_and_row_when_found(self) -> None:
        row = ProjectRow(
            id=42,
            name="my_project",
            path="/path/to/project",
            created_at="2025-05-10T00:00:00Z",
            archived_at=None,
        )
        registry = MagicMock()
        registry.resolve_by_name.return_value = row

        project_id, returned_row = resolve_project(registry, "my_project")

        assert project_id == 42
        assert returned_row is row

    def test_raises_when_project_not_found(self) -> None:
        registry = MagicMock()
        registry.resolve_by_name.return_value = None

        with pytest.raises(ProjectResolutionError) as exc_info:
            resolve_project(registry, "nonexistent")

        assert "project not found: nonexistent" in str(exc_info.value)

    def test_raises_when_project_is_archived(self) -> None:
        row = ProjectRow(
            id=42,
            name="archived_project",
            path="/path/to/project",
            created_at="2025-05-10T00:00:00Z",
            archived_at="2025-05-15T00:00:00Z",
        )
        registry = MagicMock()
        registry.resolve_by_name.return_value = row

        with pytest.raises(ProjectResolutionError) as exc_info:
            resolve_project(registry, "archived_project")

        assert "archived and cannot be used" in str(exc_info.value)
        assert "archived_project" in str(exc_info.value)

    def test_calls_registry_with_correct_name(self) -> None:
        registry = MagicMock()
        registry.resolve_by_name.return_value = None

        with pytest.raises(ProjectResolutionError):
            resolve_project(registry, "test_name")

        registry.resolve_by_name.assert_called_once_with("test_name")

    def test_project_resolution_error_is_lookup_error(self) -> None:
        assert issubclass(ProjectResolutionError, LookupError)
