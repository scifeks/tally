"""Report generation command for the tally REPL."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from application.chat.stream_composer import RagUnavailable
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from core.project_paths import ProjectPaths
from factories.persistence import (
    ProjectNotFound,
    create_findings_service,
    create_reports_service,
    make_store,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from application.rag.knowledge_base import FindingKnowledgeBase
    from application.repl.interface import REPL


def _project_paths(repl: REPL) -> ProjectPaths:
    assert repl.active_project is not None
    return ProjectPaths.from_canonical(repl.base_path, repl.active_project)


class ReportCommand:
    """Handler for the 'report' REPL command."""

    def __init__(self, repl: REPL) -> None:
        self.repl = repl

    # Command entry point

    def execute(self, _cmd: str, args: list[str]) -> None:
        """Dispatch report subcommands: draft, shell, or full report (PDF default)."""
        if args and args[0] == "assemble":
            self.repl.console.print(
                "[yellow]'report assemble' has been removed.[/yellow] "
                "Use [cyan]report[/cyan] instead. PDF is now the default format."
            )
            return
        if args and args[0] == "draft":
            self._cmd_draft(args[1:])
            return
        if args and args[0] == "shell":
            self._cmd_shell(args[1:])
            return
        self._cmd_full_report(args)

    # Subcommands

    def _cmd_assemble(self, args: list[str]) -> None:
        """report assemble [--testing-type <type>]
                           [--engagement-date <YYYY-MM-DD>] [--output <path>]

        Generate the full PDF report.
        """
        from application.ports.pdf_renderer import PdfRenderError
        from application.repl.adapters.rich_console_prompt import (
            RichConsolePromptAdapter,
        )
        from application.reporting.assembler import TEMPLATES_DIR
        from application.reporting.orchestrator import (
            ReportOverwriteDenied,
            ReportRequest,
            run_report,
        )
        from application.reporting.resolver import SectionMissingError
        from infrastructure.reporting.jinja2_template_renderer import (
            Jinja2TemplateRenderer,
        )
        from infrastructure.reporting.weasyprint_pdf_renderer import (
            WeasyPrintPdfRenderer,
        )

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
            report_dir = _project_paths(self.repl).reports_dir
            report_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(report_dir / f"{self.repl.active_project}-report.pdf")

        force_overwrite = False
        if Path(output_path).exists():
            prompt = RichConsolePromptAdapter()
            self.repl.console.print(f"Report already exists at {output_path!r}.")
            if not prompt.confirm("Overwrite?"):
                self.repl.console.print("[yellow]Assembly cancelled.[/yellow]")
                return
            force_overwrite = True

        logger.info("Assembling report for project %r", self.repl.active_project)
        request = ReportRequest(
            project=self.repl.active_project,
            base_path=Path(self.repl.base_path),
            format="pdf",
            output_path=Path(output_path),
            testing_type=testing_type,
            engagement_date=engagement_date,
            force_overwrite=force_overwrite,
        )
        try:
            with self.repl.console.status("Rendering PDF..."):
                _, fr, _, _ = make_store(
                    self.repl.base_path,
                    self.repl.active_project,
                )
                run_report(
                    request,
                    prompt=RichConsolePromptAdapter(),
                    finding_repo=fr,
                    template_renderer=Jinja2TemplateRenderer(TEMPLATES_DIR),
                    pdf_renderer=WeasyPrintPdfRenderer(),
                )
        except SectionMissingError as exc:
            self.repl.console.print(f"[red]Section missing:[/red] {exc}")
            return
        except PdfRenderError as exc:
            self.repl.console.print(f"[red]PDF render error:[/red] {exc}")
            return
        except ReportOverwriteDenied as exc:
            self.repl.console.print(f"[yellow]{exc}[/yellow]")
            return

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

        try:
            kb = self._get_knowledge_base()
        except RagUnavailable as exc:
            self.repl.console.print(f"[red]RAG error:[/red] {exc}")
            return

        try:
            finding_repo = create_findings_service(
                self.repl.project_registry, self._resolve_project_id()
            ).finding_repo
        except (ProjectNotFound, ValueError) as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return

        if output_path is None:
            ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
            ext = "md" if fmt == "markdown" else fmt
            reports_dir = _project_paths(self.repl).reports_dir
            reports_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(reports_dir / f"report_{ts}.{ext}")

        from application.reporting.generator import ReportGenerator

        generator = ReportGenerator(kb, self.repl.active_project, finding_repo)

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
        from application.repl.adapters.console_draft_sink import ConsoleDraftEventSink
        from application.repl.adapters.rich_console_prompt import (
            RichConsolePromptAdapter,
        )
        from application.reporting.draft_orchestrator import (
            DraftCancelled,
            DraftGenerationError,
            DraftOverwriteDenied,
            DraftRequest,
            run_draft,
        )
        from application.reporting.drafts import SECTION_REGISTRY

        force = "--force" in args
        skip_triage = "--skip-triage" in args
        args = [a for a in args if a not in ("--force", "--skip-triage")]

        if not self.repl.active_project:
            self.repl.console.print(
                "[yellow]No active project. "
                "Use 'project add' or 'project switch <name>' first.[/yellow]"
            )
            return

        sections = [args[0]] if args else list(SECTION_REGISTRY.keys())

        try:
            draft_repo = create_reports_service(
                self.repl.project_registry, self._resolve_project_id()
            ).draft_repo
        except (ProjectNotFound, ValueError) as exc:
            self.repl.console.print(f"[red]Project error:[/red] {exc}")
            return

        prompt = RichConsolePromptAdapter()
        sink = ConsoleDraftEventSink(self.repl.console)

        for section in sections:
            request = DraftRequest(
                project=self.repl.active_project,
                base_path=Path(self.repl.base_path),
                section=section,
                force_overwrite=force,
                skip_triage=skip_triage,
            )
            try:
                paths = _project_paths(self.repl)
                _, fr, _, _ = make_store(
                    self.repl.base_path,
                    self.repl.active_project,
                )
                from factories.persistence import (
                    create_repo_repo,
                )

                rr = create_repo_repo(paths.findings_db)
                run_draft(
                    request,
                    prompt=prompt,
                    repo=draft_repo,
                    finding_repo=fr,
                    repo_repo=rr,
                    event_sink=sink,
                )
            except DraftOverwriteDenied as exc:
                self.repl.console.print(f"[yellow]{exc}[/yellow]")
            except DraftCancelled as exc:
                self.repl.console.print(f"[yellow]{exc}[/yellow]")
                break
            except DraftGenerationError as exc:
                self.repl.console.print(f"[red]Error:[/red] {exc}")
            except ValueError as exc:
                self.repl.console.print(f"[red]Invalid section:[/red] {exc}")

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

        from application.ports.pdf_renderer import PdfRenderError
        from application.reporting.assembler import TEMPLATES_DIR, ReportAssembler
        from application.reporting.resolver import SectionMissingError
        from infrastructure.reporting.jinja2_template_renderer import (
            Jinja2TemplateRenderer,
        )
        from infrastructure.reporting.weasyprint_pdf_renderer import (
            WeasyPrintPdfRenderer,
        )

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

        from application.repl.adapters.rich_console_prompt import (
            RichConsolePromptAdapter,
        )

        _, fr, _, _ = make_store(
            self.repl.base_path,
            self.repl.active_project,
        )
        assembler = ReportAssembler(
            project=self.repl.active_project,
            base_path=self.repl.base_path,
            prompt=RichConsolePromptAdapter(),
            template_renderer=Jinja2TemplateRenderer(TEMPLATES_DIR),
            pdf_renderer=WeasyPrintPdfRenderer(),
            finding_repo=fr,
            testing_type=testing_type,
            engagement_date=engagement_date,
        )

        try:
            context = assembler.build_context()
        except SectionMissingError as exc:
            self.repl.console.print(f"[red]Section missing:[/red] {exc}")
            return

        try:
            with self.repl.console.status("Rendering PDF..."):
                pdf_bytes = assembler.render_pdf(context)
        except PdfRenderError as exc:
            self.repl.console.print(f"[red]PDF render error:[/red] {exc}")
            return

        Path(output_path).write_bytes(pdf_bytes)
        self.repl.console.print(f"[green]Shell report saved:[/green] {output_path}")

    # Private helpers

    def _check_drafts_present(self) -> bool:
        """Return True if every draft section has at least a draft or reviewed file.

        If any section is missing entirely, print guidance and return False.
        """
        from application.reporting.drafts import SECTION_REGISTRY

        paths = _project_paths(self.repl)
        base = paths.reports_dir
        missing = [
            section
            for section in SECTION_REGISTRY
            if not (paths.reports_draft_dir / f"{section}.md").exists()
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

    def _get_knowledge_base(self) -> FindingKnowledgeBase:
        """Return the per-project FindingKnowledgeBase.

        Raises RagUnavailable if ChromaDB or the embedding/LLM provider
        cannot be reached. The shared cache stores both successful
        builds and prior failures.
        """
        assert self.repl.active_project is not None
        knowledge_base = get_or_build_knowledge_base(
            self.repl.knowledge_base_cache,
            self.repl.active_project,
            self.repl.base_path,
        )
        if knowledge_base is None:
            raise RagUnavailable(
                "RAG engine unavailable for this project; "
                "ChromaDB or embedding provider is not reachable"
            )
        return knowledge_base

    def _resolve_project_id(self) -> int:
        assert self.repl.active_project is not None
        row = self.repl.project_registry.resolve_by_name(self.repl.active_project)
        if row is None:
            raise ValueError(f"project not found: {self.repl.active_project}")
        return row.id

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
