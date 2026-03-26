"""Report generation command for the tally REPL."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from application.rag.engine import RAGEngine
    from application.repl.interface import REPL


class ReportCommand:
    """Handler for the 'report' REPL command."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # ------------------------------------------------------------------
    # Command entry point
    # ------------------------------------------------------------------

    def execute(self, _cmd: str, args: list[str]) -> None:
        """Dispatch report subcommands: draft, shell, or full report (PDF default)."""
        if args and args[0] == "assemble":
            self.repl.console.print(
                "[yellow]'report assemble' has been removed.[/yellow] "
                "Use [cyan]report[/cyan] instead — PDF is now the default format."
            )
            return
        if args and args[0] == "draft":
            self._cmd_draft(args[1:])
            return
        if args and args[0] == "shell":
            self._cmd_shell(args[1:])
            return
        self._cmd_full_report(args)

    # ------------------------------------------------------------------
    # Subcommands
    # ------------------------------------------------------------------

    def _cmd_assemble(self, args: list[str]) -> None:
        """report assemble [--testing-type <type>]
                           [--engagement-date <YYYY-MM-DD>] [--output <path>]

        Assembles the full PDF report with all findings content populated.
        Finding IDs are reset and reassigned at the start of every run.
        Draft/reviewed sections are resolved as in 'report shell'.

        Company name is read from the active project's configuration.
        Testing types: white_box, grey_box, black_box (default: white_box).
        Default output: projects/<project>/report/<project>-report.pdf.
        """
        from application.reporting.assembler import ReportAssembler
        from application.reporting.pdf import PDFRenderError
        from application.reporting.resolver import SectionMissingError

        testing_type, args = self._parse_value_flag(args, "--testing-type")
        engagement_date, args = self._parse_value_flag(args, "--engagement-date")
        output_path, args = self._parse_value_flag(args, "--output")

        testing_type = testing_type or "white_box"

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        if output_path is None:
            report_dir = (
                Path(self.repl.base_path)
                / "projects"
                / self.repl.active_project
                / "reports"
            )
            report_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(report_dir / f"{self.repl.active_project}-report.pdf")

        if Path(output_path).exists():
            answer = input(
                f"Report already exists at {output_path!r}. Overwrite? [y/N] "
            )
            if answer.strip().lower() not in ("y", "yes"):
                self.repl.console.print("[yellow]Assembly cancelled.[/yellow]")
                return

        assembler = ReportAssembler(
            project=self.repl.active_project,
            base_path=self.repl.base_path,
            testing_type=testing_type,
            engagement_date=engagement_date,
        )

        # build_context() may call input() for draft confirmations — run
        # outside the spinner so prompts are visible.
        logger.info("Assembling report for project %r", self.repl.active_project)
        try:
            context = assembler.build_context()
        except SectionMissingError as exc:
            self.repl.console.print(f"[red]Section missing:[/red] {exc}")
            return

        logger.info("Rendering PDF to %r", output_path)
        try:
            with self.repl.console.status("Rendering PDF..."):
                pdf_bytes = assembler.render_pdf(context)
        except PDFRenderError as exc:
            self.repl.console.print(f"[red]PDF render error:[/red] {exc}")
            return

        Path(output_path).write_bytes(pdf_bytes)
        logger.info("PDF written: %s", output_path)
        self.repl.console.print(f"[green]Report saved:[/green] {output_path}")

    def _cmd_full_report(self, args: list[str]) -> None:
        """Generate a full structured report (pdf / markdown / html / json)."""
        fmt, args = self._parse_value_flag(args, "--format")
        output_path, args = self._parse_value_flag(args, "--output")
        testing_type, args = self._parse_value_flag(args, "--testing-type")
        engagement_date, args = self._parse_value_flag(args, "--engagement-date")

        fmt = fmt or "pdf"

        if fmt == "pdf":
            if not self.repl.active_project:
                self.repl.console.print(
                    "[yellow]No active project. "
                    "Use 'project add' or 'project switch <name>' first.[/yellow]"
                )
                return
            if not self._check_drafts_present():
                return
            assemble_args = []
            if output_path:
                assemble_args += ["--output", output_path]
            if testing_type:
                assemble_args += ["--testing-type", testing_type]
            if engagement_date:
                assemble_args += ["--engagement-date", engagement_date]
            self._cmd_assemble(assemble_args)
            return

        if fmt not in ("markdown", "html", "json"):
            self.repl.console.print(
                f"[red]Unknown format:[/red] {fmt!r}. "
                "Use pdf (default), markdown, html, or json."
            )
            return

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        rag_engine = self._get_rag_engine()
        if rag_engine is None:
            return

        if output_path is None:
            ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
            ext = "md" if fmt == "markdown" else fmt
            reports_dir = (
                Path(self.repl.base_path)
                / "projects"
                / self.repl.active_project
                / "reports"
            )
            reports_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(reports_dir / f"report_{ts}.{ext}")

        from application.reporting.generator import ReportGenerator
        from infrastructure.store import make_store

        _, finding_repo, _, _ = make_store(
            self.repl.base_path, self.repl.active_project
        )
        generator = ReportGenerator(rag_engine, self.repl.active_project, finding_repo)

        with self.repl.console.status(f"Generating {fmt} report..."):
            generator.generate(output_format=fmt, output_path=output_path)

        self.repl.console.print(f"[green]✓ Report saved:[/green] {output_path}")

    def _cmd_draft(self, args: list[str]) -> None:
        """report draft [<section>] [--force]

        Generates LLM-drafted markdown file(s) for report section(s).
        Draft files are written to projects/<project>/reports/draft/<section>.md.

        With no <section> argument, drafts every section in order.
        With a <section> argument, drafts only that section.

        Valid sections:
          executive-summary       2-3 paragraph non-technical summary
          risk-level              Single paragraph on the overall risk rating
          critical-issues         Top 3-5 findings described in plain English
          improvement-points      Recurring vulnerability themes
          scope-and-methodology   What was tested and how
          general-recommendations Actionable recommendations grouped by theme
        """
        from application.reporting.draft_runner import (
            generate_draft,
            get_all_sections,
        )

        force = "--force" in args
        skip_triage = "--skip-triage" in args
        args = [a for a in args if a not in ("--force", "--skip-triage")]

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        sections = [args[0]] if args else get_all_sections()

        for section in sections:
            generate_draft(
                section=section,
                project=self.repl.active_project,
                base_path=self.repl.base_path,
                console=self.repl.console,
                force=force,
                skip_triage=skip_triage,
            )

    def _cmd_shell(self, args: list[str]) -> None:
        """report shell [--testing-type <type>]
                        [--engagement-date <YYYY-MM-DD>] [--output <path>]

        Generates a shell PDF with all section placeholders in place.
        LLM-drafted sections are resolved from the project's draft/reviewed
        directories; Segment 4/5 placeholders are left empty.

        Company name is read from the active project's configuration.
        Useful for visually inspecting layout, typography, and CSS before
        Segment 4/5 content is wired in.

        Testing types: white_box, grey_box, black_box (default: white_box).
        Output defaults to /tmp/tally_shell_report.pdf.
        """
        from pathlib import Path

        from application.reporting.assembler import ReportAssembler
        from application.reporting.pdf import PDFRenderError
        from application.reporting.resolver import SectionMissingError

        testing_type, args = self._parse_value_flag(args, "--testing-type")
        engagement_date, args = self._parse_value_flag(args, "--engagement-date")
        output_path, args = self._parse_value_flag(args, "--output")

        testing_type = testing_type or "white_box"
        output_path = output_path or "/tmp/tally_shell_report.pdf"

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        assembler = ReportAssembler(
            project=self.repl.active_project,
            base_path=self.repl.base_path,
            testing_type=testing_type,
            engagement_date=engagement_date,
        )

        # build_context() calls input() for any section that has no reviewed
        # copy — those prompts must be visible, so run it outside the spinner.
        try:
            context = assembler.build_context()
        except SectionMissingError as exc:
            self.repl.console.print(f"[red]Section missing:[/red] {exc}")
            return

        try:
            with self.repl.console.status("Rendering PDF..."):
                pdf_bytes = assembler.render_pdf(context)
        except PDFRenderError as exc:
            self.repl.console.print(f"[red]PDF render error:[/red] {exc}")
            return

        Path(output_path).write_bytes(pdf_bytes)
        self.repl.console.print(f"[green]Shell report saved:[/green] {output_path}")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_drafts_present(self) -> bool:
        """Return True if every draft section has at least a draft or reviewed file.

        If any section is missing entirely, print guidance and return False.
        """
        from application.reporting.draft_runner import get_all_sections

        assert self.repl.active_project is not None
        base = (
            Path(self.repl.base_path)
            / "projects"
            / self.repl.active_project
            / "reports"
        )
        missing = [
            section
            for section in get_all_sections()
            if not (base / "draft" / f"{section}.md").exists()
            and not (base / "reviewed" / f"{section}.md").exists()
        ]
        if missing:
            self.repl.console.print(
                "[yellow]The following sections have not been drafted yet:[/yellow]"
            )
            for s in missing:
                self.repl.console.print(f"  • {s}")
            self.repl.console.print(
                "\nRun [cyan]report draft[/cyan] to generate all sections, "
                "then review them before generating the final report."
            )
            return False
        return True

    def _get_rag_engine(self) -> RAGEngine | None:
        """Create and return a RAGEngine for the active project, or None on error."""
        from application.rag import RAGEngine

        assert self.repl.active_project is not None
        try:
            return RAGEngine(
                project_name=self.repl.active_project,
                base_path=self.repl.base_path,
            )
        except RuntimeError as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return None
        except ValueError as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return None

    @staticmethod
    def _parse_value_flag(args: list[str], *flags: str) -> tuple[str | None, list[str]]:
        """Extract a value flag (e.g. --format markdown or --format=markdown).

        Returns (value_or_None, remaining_args).
        """
        for i, token in enumerate(args):
            # Space-separated form: --flag value
            if token in flags and i + 1 < len(args):
                value = args[i + 1]
                return value, args[:i] + args[i + 2 :]
            # Equals form: --flag=value
            for flag in flags:
                if token.startswith(f"{flag}="):
                    value = token[len(flag) + 1 :]
                    return value, args[:i] + args[i + 1 :]
        return None, args
