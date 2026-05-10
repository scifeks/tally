"""Unit tests for the ToolOverride -> CommandEntry mapper used by
discover_tools' DB-overlay branch."""

from __future__ import annotations

from core.config.schemas import CommandEntry
from domain.tool_overrides.entry import ToolOverride


class TestOverrideToCommandEntry:
    def test_local_override_maps_to_command_entry(self) -> None:
        from application.tools.registry import _override_to_command_entry

        override = ToolOverride(
            id=1,
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/usr/local/bin/semgrep",
            container_name=None,
            container_tool_path=None,
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )
        entry = _override_to_command_entry(override)
        assert isinstance(entry, CommandEntry)
        assert entry.location == "local"
        assert entry.path == "/usr/local/bin/semgrep"
        assert entry.container is None

    def test_docker_override_maps_to_command_entry(self) -> None:
        from application.tools.registry import _override_to_command_entry

        override = ToolOverride(
            id=2,
            tool_name="gitleaks",
            args_mode="custom",
            type="repo",
            location="docker",
            path=None,
            container_name="tally-gitleaks",
            container_tool_path="/usr/local/bin/gitleaks",
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )
        entry = _override_to_command_entry(override)
        assert entry.location == "docker"
        assert entry.path == ""
        assert entry.container is not None
        assert entry.container.name == "tally-gitleaks"
        assert entry.container.tool_path == "/usr/local/bin/gitleaks"

    def test_args_mode_is_dropped_from_command_entry(self) -> None:
        from application.tools.registry import _override_to_command_entry

        override = ToolOverride(
            id=3,
            tool_name="bandit",
            args_mode="custom",
            type="repo",
            location="local",
            path="/usr/local/bin/bandit",
            container_name=None,
            container_tool_path=None,
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )
        entry = _override_to_command_entry(override)
        assert not hasattr(entry, "args_mode")


class _FakeOverridesRepo:
    """Minimal fake for ToolOverridesRepositoryPort testing."""

    def __init__(self, rows: list[ToolOverride], total: int) -> None:
        self._rows = rows
        self._total = total
        self.calls: list[tuple[int, int]] = []

    def list_paginated(
        self, *, offset: int = 0, limit: int = 50
    ) -> tuple[list[ToolOverride], int]:
        self.calls.append((offset, limit))
        return self._rows, self._total

    def get_by_tool_name(self, tool_name: str) -> ToolOverride | None:
        return None

    def insert(
        self,
        *,
        tool_name: str,
        args_mode: str,
        type: str,
        location: str,
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
    ) -> int:
        return 0

    def update(
        self,
        tool_name: str,
        *,
        args_mode: str,
        type: str,
        location: str,
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
    ) -> None:
        pass

    def delete(self, tool_name: str) -> None:
        pass


class TestDiscoverToolsOverlay:
    def test_db_overlay_replaces_global_entry(self, tmp_path, monkeypatch) -> None:
        from application.tools.registry import ToolRegistry, discover_tools

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "commands.json"

        global_config = {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/global/path/semgrep",
            }
        }
        import json

        config_file.write_text(json.dumps(global_config))

        override = ToolOverride(
            id=1,
            tool_name="semgrep",
            args_mode="stock",
            type="repo",
            location="local",
            path="/override/path/semgrep",
            container_name=None,
            container_tool_path=None,
            created_at="2026-05-04T00:00:00Z",
            updated_at="2026-05-04T00:00:00Z",
        )
        fake_repo = _FakeOverridesRepo([override], 1)

        registry = ToolRegistry()
        discover_tools(
            registry,
            base_path=str(tmp_path),
            project_name="test_project",
            overrides_repo=fake_repo,
        )

        config = registry.get_tool_config("semgrep")
        assert config is not None
        assert config.path == "/override/path/semgrep"
        assert fake_repo.calls == [(0, 10_000)]

    def test_db_overlay_skipped_when_repo_is_none(self, tmp_path, monkeypatch) -> None:
        from application.tools.registry import ToolRegistry, discover_tools

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "commands.json"

        global_config = {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/global/path/semgrep",
            }
        }
        import json

        config_file.write_text(json.dumps(global_config))

        registry = ToolRegistry()
        discover_tools(
            registry,
            base_path=str(tmp_path),
            project_name="test_project",
            overrides_repo=None,
        )

        config = registry.get_tool_config("semgrep")
        assert config is not None
        assert config.path == "/global/path/semgrep"

    def test_db_overlay_raises_when_repo_returns_more_than_ceiling(
        self, tmp_path
    ) -> None:
        from application.tools.registry import ToolRegistry, discover_tools

        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "commands.json"

        global_config = {
            "semgrep": {
                "type": "repo",
                "location": "local",
                "path": "/global/path/semgrep",
            }
        }
        import json

        config_file.write_text(json.dumps(global_config))

        fake_repo = _FakeOverridesRepo([], 10_001)

        registry = ToolRegistry()
        import pytest

        with pytest.raises(RuntimeError) as exc_info:
            discover_tools(
                registry,
                base_path=str(tmp_path),
                project_name="test_project",
                overrides_repo=fake_repo,
            )

        assert "tool_overrides has 10001 rows" in str(exc_info.value)
        assert "exceeds discover_tools ceiling" in str(exc_info.value)
