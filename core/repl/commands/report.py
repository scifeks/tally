"""Report generation command for the tally REPL."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from core.repl.interface import REPL
    from core.rag.engine import RAGEngine


class ReportCommand:
    """Handler for the 'report' REPL command."""

    def __init__(self, repl: 'REPL') -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------

    def execute(self, _cmd: str, args: List[str]) -> None:
        """report [--format markdown|html|json] [--output <path>]"""
        fmt, args = self._parse_value_flag(args, '--format')
        output_path, args = self._parse_value_flag(args, '--output')

        fmt = fmt or 'markdown'

        if fmt not in ('markdown', 'html', 'json'):
            self.repl.console.print(
                f'[red]Unknown format:[/red] {fmt!r}. Use markdown, html, or json.'
            )
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return

        if output_path is None:
            ts = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')
            ext = 'md' if fmt == 'markdown' else fmt
            reports_dir = (
                Path(self.repl.base_path)
                / 'projects'
                / self.repl.active_project
                / 'reports'
            )
            reports_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(reports_dir / f'report_{ts}.{ext}')

        from core.reporting.generator import ReportGenerator

        generator = ReportGenerator(rag_engine, self.repl.active_project)

        with self.repl.console.status(f'Generating {fmt} report...'):
            generator.generate(output_format=fmt, output_path=output_path)

        self.repl.console.print(f'[green]✓ Report saved:[/green] {output_path}')

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_rag_engine(self) -> Optional['RAGEngine']:
        """Create and return a RAGEngine for the active project, or None on error."""
        from core.rag import RAGEngine

        try:
            return RAGEngine(
                project_name=self.repl.active_project,
                base_path=self.repl.base_path,
            )
        except RuntimeError as exc:
            self.repl.console.print(f'[red]RAG error:[/red] {exc}')
            return None
        except ValueError as exc:
            self.repl.console.print(f'[red]Project error:[/red] {exc}')
            return None

    @staticmethod
    def _parse_value_flag(
        args: List[str], *flags: str
    ) -> tuple[Optional[str], List[str]]:
        """Extract a value flag (e.g. --format markdown). Returns (value_or_None, remaining_args)."""
        for i, token in enumerate(args):
            if token in flags and i + 1 < len(args):
                value = args[i + 1]
                remaining = args[:i] + args[i + 2:]
                return value, remaining
        return None, args
