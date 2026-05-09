"""Tests triage help notices."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from application.repl.help_renderer import HelpRenderer
from application.triage.readiness import TriageReadiness


def _readiness(
    *,
    provider: str = "claude_code",
    enabled: bool = True,
    reason: str | None = None,
) -> TriageReadiness:
    labels = {
        "claude_code": "Claude Code",
        "open_code": "OpenCode",
    }
    return TriageReadiness(
        provider=provider,
        backend_label=labels.get(provider),
        enabled=enabled,
        reason=reason,
    )


def _render_table(
    *,
    readiness: TriageReadiness,
) -> str:
    buf = StringIO()
    console = Console(file=buf, highlight=False, markup=True, width=200)
    renderer = HelpRenderer(console, triage_readiness=readiness)
    renderer.render_all()
    return buf.getvalue()


class TestHelpRendererClaudeConfigured:
    def test_triage_rows_not_dimmed_when_ready(self) -> None:
        output = _render_table(
            readiness=_readiness(enabled=True),
        )
        assert "(Claude Code required for Triage)" not in output

    def test_triage_rows_show_notice_when_docker_missing(
        self,
    ) -> None:
        output = _render_table(
            readiness=_readiness(
                enabled=False,
                reason="Docker is not installed or not running",
            ),
        )
        assert "Docker is not installed" in output


class TestHelpRendererOtherProviders:
    def test_disabled_triage_shows_disabled_notice(self) -> None:
        output = _render_table(
            readiness=_readiness(
                provider="",
                enabled=False,
                reason="Triage disabled in config",
            ),
        )
        assert "Triage disabled in config" in output

    def test_open_code_not_dimmed_when_ready(self) -> None:
        output = _render_table(
            readiness=_readiness(provider="open_code", enabled=True),
        )
        assert "(OpenCode required for Triage)" not in output

    def test_open_code_dimmed_when_docker_missing(self) -> None:
        output = _render_table(
            readiness=_readiness(
                provider="open_code",
                enabled=False,
                reason="Docker is not installed or not running",
            ),
        )
        assert "Docker is not installed" in output

    def test_non_triage_rows_unaffected(self) -> None:
        output = _render_table(
            readiness=_readiness(
                provider="",
                enabled=False,
                reason="Triage disabled in config",
            ),
        )
        assert "project add" in output
        assert "scan" in output
