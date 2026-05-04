"""Integration tests for ToolOverridesService."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.ports.tool_overrides import ToolOverrideNameConflict
from application.tool_overrides.service import (
    ToolOverrideNotFound,
    ToolOverridesService,
    ToolOverrideValidationError,
)
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.tool_overrides import (
    ToolOverridesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def factory(tmp_path: Path) -> ConnectionFactory:
    f = ConnectionFactory(tmp_path / "findings.db")
    f.init_schema()
    return f


@pytest.fixture()
def service(factory: ConnectionFactory) -> ToolOverridesService:
    repo = ToolOverridesRepository(factory)
    return ToolOverridesService(repo)


class TestToolOverridesServiceIntegration:
    def test_create_local_round_trip(self, service: ToolOverridesService) -> None:
        result = service.create(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/local/bin/semgrep",
        )

        assert result.tool_name == "semgrep"
        assert result.args_mode == "stock"
        assert result.location == "local"
        assert result.path == "/usr/local/bin/semgrep"
        assert result.container_name is None
        assert result.container_tool_path is None

    def test_create_docker_round_trip_normalizes_path_to_none(
        self, service: ToolOverridesService
    ) -> None:
        result = service.create(
            tool_name="gitleaks",
            args_mode="custom",
            type="repo",
            location="docker",
            path="should-be-cleared",
            container_name="gitleaks-runner",
            container_tool_path="/usr/bin/gitleaks",
        )

        assert result.location == "docker"
        assert result.path is None
        assert result.container_name == "gitleaks-runner"
        assert result.container_tool_path == "/usr/bin/gitleaks"

    def test_create_unique_conflict_is_typed(
        self, service: ToolOverridesService
    ) -> None:
        service.create(
            tool_name="dup",
            args_mode="stock",
            type="repo",
            location="local",
            path="/x",
        )

        with pytest.raises(ToolOverrideNameConflict) as exc:
            service.create(
                tool_name="dup",
                args_mode="stock",
                type="repo",
                location="local",
                path="/y",
            )

        assert exc.value.tool_name == "dup"

    def test_create_validation_error_persists_nothing(
        self, service: ToolOverridesService
    ) -> None:
        with pytest.raises(ToolOverrideValidationError):
            service.create(
                tool_name="semgrep",
                args_mode="stock",
                type="repo",
                location="local",
                path="",
            )

        rows, total = service.list()
        assert total == 0
        assert rows == []

    def test_replace_swaps_local_to_docker_and_clears_path(
        self, service: ToolOverridesService
    ) -> None:
        service.create(
            tool_name="zap",
            args_mode="stock",
            type="api",
            location="local",
            path="/usr/bin/zap",
        )

        result = service.replace(
            "zap",
            args_mode="stock",
            type="api",
            location="docker",
            container_name="zap-runner",
            container_tool_path="/zap/zap.sh",
        )

        assert result.location == "docker"
        assert result.path is None
        assert result.container_name == "zap-runner"
        assert result.container_tool_path == "/zap/zap.sh"

    def test_replace_swaps_docker_to_local_and_clears_container(
        self, service: ToolOverridesService
    ) -> None:
        service.create(
            tool_name="zap",
            args_mode="stock",
            type="api",
            location="docker",
            container_name="zap-runner",
            container_tool_path="/zap/zap.sh",
        )

        result = service.replace(
            "zap",
            args_mode="stock",
            type="api",
            location="local",
            path="/usr/bin/zap",
        )

        assert result.location == "local"
        assert result.path == "/usr/bin/zap"
        assert result.container_name is None
        assert result.container_tool_path is None

    def test_replace_missing_raises_not_found(
        self, service: ToolOverridesService
    ) -> None:
        with pytest.raises(ToolOverrideNotFound) as exc:
            service.replace(
                "ghost",
                args_mode="stock",
                type="repo",
                location="local",
                path="/x",
            )

        assert exc.value.tool_name == "ghost"

    def test_delete_removes_row(self, service: ToolOverridesService) -> None:
        service.create(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/x",
        )
        service.delete("semgrep")
        assert service.get("semgrep") is None

    def test_delete_silent_when_missing(self, service: ToolOverridesService) -> None:
        service.delete("never-existed")

    def test_delete_unconstrained_when_saved_scan_references_tool(
        self,
        service: ToolOverridesService,
        factory: ConnectionFactory,
    ) -> None:
        service.create(
            tool_name="semgrep",
            args_mode="custom",
            type="repo",
            location="local",
            path="/usr/local/bin/semgrep",
        )
        with factory.connect() as conn:
            cur = conn.execute("INSERT INTO saved_scans (name) VALUES (?)", ("weekly",))
            conn.execute(
                "INSERT INTO saved_scan_tools (saved_scan_id, tool_name) VALUES (?, ?)",
                (cur.lastrowid, "semgrep"),
            )

        service.delete("semgrep")

        assert service.get("semgrep") is None

    def test_list_returns_total_and_rows(self, service: ToolOverridesService) -> None:
        for name in ("a", "b", "c"):
            service.create(
                tool_name=name,
                args_mode="stock",
                type="repo",
                location="local",
                path=f"/{name}",
            )

        rows, total = service.list()
        assert total == 3
        assert {r.tool_name for r in rows} == {"a", "b", "c"}

    def test_full_round_trip(self, service: ToolOverridesService) -> None:
        created = service.create(
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/bin/semgrep",
        )
        fetched = service.get("semgrep")
        assert fetched == created

        replaced = service.replace(
            "semgrep",
            args_mode="custom",
            type="repo",
            location="docker",
            container_name="runner",
            container_tool_path="/usr/bin/semgrep",
        )
        assert replaced.args_mode == "custom"
        assert replaced.location == "docker"
        assert replaced.container_name == "runner"

        service.delete("semgrep")
        assert service.get("semgrep") is None
