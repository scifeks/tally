"""Tests triage help notices."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from rich.console import Console

from application.repl.help_renderer import HelpRenderer

_MISSING = object()


def _runtime_service(installed: bool) -> MagicMock:
    svc = MagicMock()
    svc.is_installed.return_value = installed
    return svc


def _write_global_config(base_path: Path, payload: dict) -> None:
    cfg_dir = base_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "global.json").write_text(json.dumps(payload))


def _render_table(
    tmp_path: Path,
    *,
    config: dict,
    installed: bool = False,
    runtime_service: MagicMock | None | object = _MISSING,
) -> str:
    _write_global_config(tmp_path, config)
    buf = StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=200)
    selected_runtime_service = (
        _runtime_service(installed) if runtime_service is _MISSING else runtime_service
    )
    renderer = HelpRenderer(
        console,
        base_path=str(tmp_path),
        runtime_service=selected_runtime_service,
    )
    renderer.render_all()
    return buf.getvalue()


class TestHelpRendererClaudeConfigured:
    def test_triage_rows_not_dimmed_when_runtime_present(self, tmp_path: Path) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": "claude_code"},
            installed=True,
        )
        assert "(Claude Code required for Triage)" not in output

    def test_triage_rows_show_backend_notice_when_runtime_missing(
        self, tmp_path: Path
    ) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": "claude_code"},
            installed=False,
        )
        assert "Claude Code required for Triage" in output


class TestHelpRendererOtherProviders:
    def test_disabled_triage_shows_disabled_notice(self, tmp_path: Path) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": ""},
            installed=True,
        )
        assert "Triage disabled in config" in output

    def test_open_code_not_dimmed_when_runtime_present(self, tmp_path: Path) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": "open_code"},
            installed=True,
        )
        assert "(OpenCode required for Triage)" not in output

    def test_open_code_dimmed_when_runtime_missing(self, tmp_path: Path) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": "open_code"},
            installed=False,
        )
        assert "OpenCode required for Triage" in output

    def test_non_triage_rows_unaffected(self, tmp_path: Path) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": ""},
            installed=False,
        )
        assert "project add" in output
        assert "scan" in output

    def test_no_runtime_service_keeps_claude_configured_rows_visible(
        self, tmp_path: Path
    ) -> None:
        output = _render_table(
            tmp_path,
            config={"triage_agent_provider": "claude_code"},
            runtime_service=None,
        )
        assert "(Claude Code required for Triage)" not in output
