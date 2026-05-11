"""Report generation command handler for the Tally CLI."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from application.chat.stream_composer import RagUnavailable
from application.cli.adapters import CliPromptAdapter
from application.cli.draft_sink import CliDraftEventSink
from application.cli.exit_codes import (
    GENERAL_ERROR,
    PROJECT_NOT_FOUND,
    SUCCESS,
)
from application.cli.project import ProjectResolutionError, resolve_project
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from application.reporting.drafts import SECTION_REGISTRY
from application.reporting.generator import ReportGenerator
from core.project_paths import ProjectPaths
from factories.persistence import (
    create_findings_service,
    create_repo_repo,
    create_reports_service,
    make_store,
)

if TYPE_CHECKING:
    from argparse import Namespace

    from application.project.registry_service import ProjectRegistryService
    from application.tools.registry import ToolRegistry


def cmd_report(
    args: Namespace,
    project_registry: ProjectRegistryService,
    tool_registry: ToolRegistry,
    base_path: Path,
) -> int:
    """Dispatch to the appropriate report subcommand."""
    del tool_registry
    if args.report_command == "draft":
        return _cmd_draft(args, project_registry, base_path)
    if args.report_command == "shell":
        return _cmd_shell(args, project_registry, base_path)
    return _cmd_full_report(args, project_registry, base_path)


def _cmd_full_report(
    args: Namespace,
    project_registry: ProjectRegistryService,
    base_path: Path,
) -> int:
    """Generate a full report in the requested format."""
    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    fmt = args.format or "pdf"

    if fmt == "pdf":
        return _assemble_pdf(args, base_path, project_name)

    if fmt not in ("markdown", "html", "json"):
        print(
            f"Unknown format: {fmt!r}. Use pdf (default), markdown, html, or json.",
            file=sys.stderr,
        )
        return GENERAL_ERROR

    return _generate_structured_report(
        args, project_registry, base_path, project_id, project_name, fmt
    )


def _assemble_pdf(
    args: Namespace,
    base_path: Path,
    project_name: str,
) -> int:
    """Assemble the final PDF from drafted sections."""
    from application.ports.pdf_renderer import PdfRenderError
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

    paths = ProjectPaths.from_canonical(str(base_path), project_name)
    missing = [
        s
        for s in SECTION_REGISTRY
        if not (paths.reports_draft_dir / f"{s}.md").exists()
        and not (paths.reports_dir / "reviewed" / f"{s}.md").exists()
    ]
    if missing:
        print("The following sections have not been drafted yet:", file=sys.stderr)
        for s in missing:
            print(f"  - {s}", file=sys.stderr)
        print(
            "\nRun 'tally report draft' to generate all sections first.",
            file=sys.stderr,
        )
        return GENERAL_ERROR

    output_path = args.output
    if output_path is None:
        report_dir = paths.reports_dir
        report_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(report_dir / f"{project_name}-report.pdf")

    testing_type = args.testing_type or "white_box"
    engagement_date = args.engagement_date

    request = ReportRequest(
        project=project_name,
        base_path=Path(base_path),
        format="pdf",
        output_path=Path(output_path),
        testing_type=testing_type,
        engagement_date=engagement_date,
        force_overwrite=True,
    )

    try:
        _, fr, _, _ = make_store(str(base_path), project_name)
        run_report(
            request,
            prompt=CliPromptAdapter(),
            finding_repo=fr,
            template_renderer=Jinja2TemplateRenderer(TEMPLATES_DIR),
            pdf_renderer=WeasyPrintPdfRenderer(),
        )
    except SectionMissingError as exc:
        print(f"Section missing: {exc}", file=sys.stderr)
        return GENERAL_ERROR
    except PdfRenderError as exc:
        print(f"PDF render error: {exc}", file=sys.stderr)
        return GENERAL_ERROR
    except ReportOverwriteDenied as exc:
        print(str(exc), file=sys.stderr)
        return GENERAL_ERROR

    print(f"Report saved: {output_path}")
    return SUCCESS


def _generate_structured_report(
    args: Namespace,
    project_registry: ProjectRegistryService,
    base_path: Path,
    project_id: int,
    project_name: str,
    fmt: str,
) -> int:
    """Generate a markdown, html, or json report via the RAG engine."""
    kb_cache: dict = {}
    try:
        kb = get_or_build_knowledge_base(kb_cache, project_name, str(base_path))
    except RagUnavailable as exc:
        print(f"RAG engine unavailable: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    if kb is None:
        print("RAG engine unavailable", file=sys.stderr)
        return GENERAL_ERROR

    try:
        finding_repo = create_findings_service(
            project_registry, project_id
        ).finding_repo
    except Exception as exc:
        print(f"Project error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    paths = ProjectPaths.from_canonical(str(base_path), project_name)
    output_path = args.output
    if output_path is None:
        ts = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        ext = "md" if fmt == "markdown" else fmt
        reports_dir = paths.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(reports_dir / f"report_{ts}.{ext}")

    generator = ReportGenerator(kb, project_name, finding_repo)
    generator.generate(output_format=fmt, output_path=output_path)
    print(f"Report saved: {output_path}")
    return SUCCESS


def _cmd_draft(
    args: Namespace,
    project_registry: ProjectRegistryService,
    base_path: Path,
) -> int:
    """Generate LLM-drafted markdown for one or all report sections."""
    from application.reporting.draft_orchestrator import (
        DraftCancelled,
        DraftGenerationError,
        DraftOverwriteDenied,
        DraftRequest,
        run_draft,
    )

    try:
        project_id, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    section = args.section
    skip_triage = args.skip_triage
    force_overwrite = True

    sections = [section] if section else list(SECTION_REGISTRY.keys())

    try:
        draft_repo = create_reports_service(project_registry, project_id).draft_repo
    except Exception as exc:
        print(f"Project error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    paths = ProjectPaths.from_canonical(str(base_path), project_name)
    _, fr, _, _ = make_store(str(base_path), project_name)
    rr = create_repo_repo(paths.findings_db)
    sink = CliDraftEventSink()

    for sec in sections:
        request = DraftRequest(
            project=project_name,
            base_path=Path(base_path),
            section=sec,
            force_overwrite=force_overwrite,
            skip_triage=skip_triage,
        )
        try:
            run_draft(
                request,
                prompt=CliPromptAdapter(),
                repo=draft_repo,
                finding_repo=fr,
                repo_repo=rr,
                event_sink=sink,
            )
        except DraftOverwriteDenied as exc:
            print(str(exc), file=sys.stderr)
        except DraftCancelled as exc:
            print(str(exc), file=sys.stderr)
            break
        except DraftGenerationError as exc:
            print(f"Error: {exc}", file=sys.stderr)
        except ValueError as exc:
            print(f"Invalid section: {exc}", file=sys.stderr)

    return SUCCESS


def _cmd_shell(
    args: Namespace,
    project_registry: ProjectRegistryService,
    base_path: Path,
) -> int:
    """Generate a shell PDF with section placeholders."""
    from application.ports.pdf_renderer import PdfRenderError
    from application.reporting.assembler import TEMPLATES_DIR, ReportAssembler
    from application.reporting.resolver import SectionMissingError
    from infrastructure.reporting.jinja2_template_renderer import (
        Jinja2TemplateRenderer,
    )
    from infrastructure.reporting.weasyprint_pdf_renderer import (
        WeasyPrintPdfRenderer,
    )

    try:
        _, project_row = resolve_project(project_registry, args.project)
        project_name = project_row.name
    except ProjectResolutionError as exc:
        print(str(exc), file=sys.stderr)
        return PROJECT_NOT_FOUND

    testing_type = args.testing_type or "white_box"
    engagement_date = args.engagement_date
    output_path = args.output or "/tmp/tally_shell_report.pdf"

    _, fr, _, _ = make_store(str(base_path), project_name)
    assembler = ReportAssembler(
        project=project_name,
        base_path=str(base_path),
        prompt=CliPromptAdapter(),
        template_renderer=Jinja2TemplateRenderer(TEMPLATES_DIR),
        pdf_renderer=WeasyPrintPdfRenderer(),
        finding_repo=fr,
        testing_type=testing_type,
        engagement_date=engagement_date,
    )

    try:
        context = assembler.build_context()
    except SectionMissingError as exc:
        print(f"Section missing: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    try:
        pdf_bytes = assembler.render_pdf(context)
    except PdfRenderError as exc:
        print(f"PDF render error: {exc}", file=sys.stderr)
        return GENERAL_ERROR

    Path(output_path).write_bytes(pdf_bytes)
    print(f"Shell report saved: {output_path}")
    return SUCCESS
