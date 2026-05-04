"""Unit tests for ToolOverridesService."""

from __future__ import annotations

from typing import Literal
from unittest.mock import MagicMock

import pytest

from application.ports.tool_overrides import ToolOverrideNameConflict
from application.tool_overrides.service import (
    FieldError,
    ToolOverrideNotFound,
    ToolOverridesService,
    ToolOverrideValidationError,
)
from domain.tool_overrides.entry import ToolOverride


def _make_override(
    override_id: int = 1,
    tool_name: str = "semgrep",
    args_mode: Literal["stock", "custom"] = "stock",
    type_: Literal["repo", "api"] = "repo",
    location: Literal["local", "docker"] = "local",
    path: str | None = "/usr/bin/semgrep",
    container_name: str | None = None,
    container_tool_path: str | None = None,
) -> ToolOverride:
    return ToolOverride(
        id=override_id,
        tool_name=tool_name,
        args_mode=args_mode,
        type=type_,
        location=location,
        path=path,
        container_name=container_name,
        container_tool_path=container_tool_path,
        created_at="2026-05-03T00:00:00+00:00",
        updated_at="2026-05-03T00:00:00+00:00",
    )


def _make_repo_mock() -> MagicMock:
    return MagicMock()


class TestThinPassThroughs:
    def test_list_delegates_to_repo(self) -> None:
        repo = _make_repo_mock()
        expected = [_make_override(), _make_override(override_id=2)]
        repo.list_paginated.return_value = (expected, 2)
        svc = ToolOverridesService(repo)

        rows, total = svc.list(offset=10, limit=20)

        repo.list_paginated.assert_called_once_with(offset=10, limit=20)
        assert rows == expected
        assert total == 2

    def test_get_delegates_to_repo(self) -> None:
        repo = _make_repo_mock()
        expected = _make_override()
        repo.get_by_tool_name.return_value = expected
        svc = ToolOverridesService(repo)

        result = svc.get("semgrep")

        repo.get_by_tool_name.assert_called_once_with("semgrep")
        assert result == expected

    def test_get_returns_none_when_repo_returns_none(self) -> None:
        repo = _make_repo_mock()
        repo.get_by_tool_name.return_value = None
        svc = ToolOverridesService(repo)

        assert svc.get("ghost") is None


class TestDelete:
    def test_delete_delegates_to_repo(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        svc.delete("semgrep")

        repo.delete.assert_called_once_with("semgrep")

    def test_delete_is_silent_when_tool_name_missing(self) -> None:
        # Repo's delete is silent on missing rows; service propagates.
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        svc.delete("never-existed")

        repo.delete.assert_called_once_with("never-existed")


class TestValidateCreate:
    def test_empty_tool_name(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="",
                args_mode="stock",
                type="repo",
                location="local",
                path="/x",
            )

        assert (
            FieldError(field="toolName", issue="must not be empty") in exc.value.fields
        )

    def test_invalid_args_mode(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="bogus",
                type="repo",
                location="local",
                path="/x",
            )

        assert any(f.field == "argsMode" for f in exc.value.fields)

    def test_invalid_type(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="bogus",
                location="local",
                path="/x",
            )

        assert any(f.field == "type" for f in exc.value.fields)

    def test_invalid_location(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="bogus",
                path="/x",
            )

        assert any(f.field == "location" for f in exc.value.fields)

    def test_local_requires_path(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="local",
                path="",
            )

        assert any(f.field == "path" for f in exc.value.fields)

    def test_docker_requires_container_name(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="docker",
                container_name=None,
                container_tool_path="/usr/bin/semgrep",
            )

        assert any(f.field == "container.name" for f in exc.value.fields)

    def test_docker_requires_container_tool_path(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="docker",
                container_name="semgrep-runner",
                container_tool_path=None,
            )

        assert any(f.field == "container.toolPath" for f in exc.value.fields)

    def test_multiple_errors_collected(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.create(
                tool_name="",
                args_mode="bogus",
                type="bogus",
                location="bogus",
            )

        assert len(exc.value.fields) >= 4


class TestCreateOrchestration:
    def test_local_create_inserts_with_path_and_clears_container(self) -> None:
        repo = _make_repo_mock()
        repo.get_by_tool_name.return_value = _make_override(
            location="local",
            path="/usr/bin/semgrep",
        )
        svc = ToolOverridesService(repo)

        svc.create(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
            container_name="should-be-cleared",
            container_tool_path="/should/be/cleared",
        )

        repo.insert.assert_called_once_with(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
            container_name=None,
            container_tool_path=None,
        )

    def test_docker_create_inserts_with_container_and_clears_path(self) -> None:
        repo = _make_repo_mock()
        repo.get_by_tool_name.return_value = _make_override(
            location="docker",
            path=None,
            container_name="semgrep-runner",
            container_tool_path="/usr/bin/semgrep",
        )
        svc = ToolOverridesService(repo)

        svc.create(
            tool_name="semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            path="should-be-cleared",
            container_name="semgrep-runner",
            container_tool_path="/usr/bin/semgrep",
        )

        repo.insert.assert_called_once_with(
            tool_name="semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            path=None,
            container_name="semgrep-runner",
            container_tool_path="/usr/bin/semgrep",
        )

    def test_create_returns_freshly_fetched_row(self) -> None:
        repo = _make_repo_mock()
        expected = _make_override()
        repo.get_by_tool_name.return_value = expected
        svc = ToolOverridesService(repo)

        result = svc.create(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
        )

        assert result == expected
        repo.get_by_tool_name.assert_called_once_with("semgrep")

    def test_create_propagates_name_conflict(self) -> None:
        repo = _make_repo_mock()
        repo.insert.side_effect = ToolOverrideNameConflict("semgrep")
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideNameConflict) as exc:
            svc.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="local",
                path="/usr/bin/semgrep",
            )

        assert exc.value.tool_name == "semgrep"


class TestValidateReplace:
    def test_empty_tool_name(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.replace(
                "",
                args_mode="stock",
                type="repo",
                location="local",
                path="/x",
            )

        assert any(f.field == "toolName" for f in exc.value.fields)

    def test_local_requires_path(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.replace(
                "semgrep",
                args_mode="stock",
                type="repo",
                location="local",
                path=None,
            )

        assert any(f.field == "path" for f in exc.value.fields)

    def test_docker_requires_both_container_fields(self) -> None:
        repo = _make_repo_mock()
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideValidationError) as exc:
            svc.replace(
                "semgrep",
                args_mode="stock",
                type="repo",
                location="docker",
            )

        names = {f.field for f in exc.value.fields}
        assert "container.name" in names
        assert "container.toolPath" in names


class TestReplaceOrchestration:
    def test_replace_raises_not_found_when_missing(self) -> None:
        repo = _make_repo_mock()
        repo.get_by_tool_name.return_value = None
        svc = ToolOverridesService(repo)

        with pytest.raises(ToolOverrideNotFound) as exc:
            svc.replace(
                "ghost",
                args_mode="stock",
                type="repo",
                location="local",
                path="/x",
            )

        assert exc.value.tool_name == "ghost"
        repo.update.assert_not_called()

    def test_replace_local_clears_container_fields(self) -> None:
        repo = _make_repo_mock()
        existing = _make_override(
            location="docker",
            path=None,
            container_name="old",
            container_tool_path="/old",
        )
        repo.get_by_tool_name.side_effect = [existing, _make_override()]
        svc = ToolOverridesService(repo)

        svc.replace(
            "semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
            container_name="should-be-cleared",
            container_tool_path="/should/be/cleared",
        )

        repo.update.assert_called_once_with(
            "semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
            container_name=None,
            container_tool_path=None,
        )

    def test_replace_docker_clears_path(self) -> None:
        repo = _make_repo_mock()
        existing = _make_override(location="local", path="/old/path")
        repo.get_by_tool_name.side_effect = [existing, _make_override()]
        svc = ToolOverridesService(repo)

        svc.replace(
            "semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            path="should-be-cleared",
            container_name="runner",
            container_tool_path="/usr/bin/semgrep",
        )

        repo.update.assert_called_once_with(
            "semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            path=None,
            container_name="runner",
            container_tool_path="/usr/bin/semgrep",
        )

    def test_replace_returns_freshly_fetched_row(self) -> None:
        repo = _make_repo_mock()
        existing = _make_override(path="/old")
        refetched = _make_override(path="/new")
        repo.get_by_tool_name.side_effect = [existing, refetched]
        svc = ToolOverridesService(repo)

        result = svc.replace(
            "semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/new",
        )

        assert result == refetched
        assert repo.get_by_tool_name.call_count == 2
