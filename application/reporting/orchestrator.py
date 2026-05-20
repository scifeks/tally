"""Orchestrate report generation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.report_repository import (
        ReportRepositoryPort,
    )

from application.locking.cancellation import CancellationToken
from application.ports.html_template_renderer import HtmlTemplateRenderer
from application.ports.pdf_renderer import PdfRenderer, PdfRenderError
from application.ports.report_event_sink import (
    NullReportEventSink,
    ReportEventSink,
)
from application.ports.user_prompt import UserPromptPort
from application.reporting.generator import ReportGenerator
from application.reporting.resolver import SectionMissingError
from domain.pipeline.report_events import (
    GenerationCancelled,
    GenerationCompleted,
    GenerationFailed,
    GenerationStarted,
    StepCompleted,
    StepStarted,
)

logger = logging.getLogger(__name__)


SUPPORTED_FORMATS = ("pdf", "markdown", "html", "json")


class ReportCancelled(Exception):
    """Raised when the orchestrator observes a cancellation between steps."""


class ReportOverwriteDenied(Exception):
    """Raised when the output path exists and force_overwrite is False."""


@dataclass(frozen=True)
class ReportRequest:
    project: str
    base_path: Path
    format: str
    output_path: Path
    testing_type: str = "white_box"
    engagement_date: str | None = None
    force_overwrite: bool = False
    company_name_override: str | None = None
    skip_triage: bool = False
    report_id: int = 0
    project_id: int | None = None
    filename: str = ""


def run_report(
    request: ReportRequest,
    *,
    prompt: UserPromptPort,
    finding_repo: FindingRepositoryPort,
    template_renderer: HtmlTemplateRenderer | None = None,
    pdf_renderer: PdfRenderer | None = None,
    event_sink: ReportEventSink | None = None,
    cancel_token: CancellationToken | None = None,
    report_repo: ReportRepositoryPort | None = None,
    retention_count: int = 0,
) -> Path:
    """Generate a report and optionally track it in report history.

    When *report_repo* is provided the orchestrator manages the full
    report row lifecycle: row creation (when ``report_id == 0``),
    status transitions, file size recording, and retention enforcement.
    """
    sink: ReportEventSink = event_sink or NullReportEventSink()
    token = cancel_token or CancellationToken()

    fmt = request.format
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unknown format: {fmt!r}. Use one of {SUPPORTED_FORMATS}.")

    if request.output_path.exists() and not request.force_overwrite:
        raise ReportOverwriteDenied(f"Report already exists at {request.output_path}")

    req = _maybe_create_row(request, report_repo)

    if report_repo and req.report_id:
        report_repo.set_status(req.report_id, "running")
        report_repo.set_started_at(req.report_id)

    sink.emit(
        GenerationStarted(
            report_id=req.report_id,
            project_id=req.project_id,
            format=fmt,
            message=f"Generating {fmt} report",
        )
    )

    try:
        if fmt == "pdf":
            if template_renderer is None or pdf_renderer is None:
                raise ValueError(
                    "template_renderer and pdf_renderer are required for pdf format"
                )
            output = _run_pdf(
                req,
                prompt,
                template_renderer,
                pdf_renderer,
                finding_repo,
                sink,
                token,
            )
        else:
            output = _run_text(req, finding_repo, sink, token)
    except ReportCancelled:
        sink.emit(
            GenerationCancelled(
                report_id=req.report_id,
                project_id=req.project_id,
                message="Report generation cancelled",
            )
        )
        _record_cancelled(req, report_repo)
        raise
    except (
        SectionMissingError,
        PdfRenderError,
        ReportOverwriteDenied,
    ) as exc:
        sink.emit(
            GenerationFailed(
                report_id=req.report_id,
                project_id=req.project_id,
                error=type(exc).__name__,
                message=str(exc),
            )
        )
        _record_failed(req, report_repo, exc)
        raise
    except Exception as exc:  # noqa: BLE001
        sink.emit(
            GenerationFailed(
                report_id=req.report_id,
                project_id=req.project_id,
                error=type(exc).__name__,
                message=str(exc),
            )
        )
        _record_failed(req, report_repo, exc)
        raise

    size = output.stat().st_size if output.exists() else 0
    sink.emit(
        GenerationCompleted(
            report_id=req.report_id,
            project_id=req.project_id,
            output_path=str(output),
            file_size_bytes=size,
            message=f"Report saved to {output}",
        )
    )
    _record_done(req, report_repo, size, retention_count)
    return output


def _maybe_create_row(
    request: ReportRequest,
    report_repo: ReportRepositoryPort | None,
) -> ReportRequest:
    """Create a report row if repo is provided and no row exists."""
    if report_repo is None or request.report_id != 0:
        return request
    filename = request.filename or request.output_path.name
    report_id = report_repo.create(
        project_id=request.project_id or 0,
        scan_run_id=None,
        format=request.format,
        filename=filename,
        filepath=str(request.output_path),
    )
    return replace(request, report_id=report_id)


def _record_done(
    request: ReportRequest,
    report_repo: ReportRepositoryPort | None,
    file_size: int,
    retention_count: int,
) -> None:
    if report_repo is None or not request.report_id:
        return
    report_repo.set_file_size(request.report_id, file_size)
    report_repo.set_status(request.report_id, "done")
    report_repo.set_finished_at(request.report_id)
    if retention_count > 0 and request.project_id:
        _enforce_retention(report_repo, request.project_id, retention_count)


def _record_failed(
    request: ReportRequest,
    report_repo: ReportRepositoryPort | None,
    exc: Exception,
) -> None:
    if report_repo is None or not request.report_id:
        return
    report_repo.set_status(request.report_id, "failed")
    report_repo.set_error(
        request.report_id,
        f"{type(exc).__name__}: {exc}",
    )
    report_repo.set_finished_at(request.report_id)


def _record_cancelled(
    request: ReportRequest,
    report_repo: ReportRepositoryPort | None,
) -> None:
    if report_repo is None or not request.report_id:
        return
    report_repo.set_status(request.report_id, "cancelled")
    report_repo.set_finished_at(request.report_id)


def _enforce_retention(
    repo: ReportRepositoryPort,
    project_id: int,
    keep: int,
) -> None:
    if keep <= 0:
        return
    try:
        rows = repo.select_for_retention(project_id, keep=keep)
    except Exception:  # noqa: BLE001
        logger.exception(
            "retention sweep failed for project %d",
            project_id,
        )
        return
    for row in rows:
        try:
            Path(row.filepath).unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "could not unlink %s during retention",
                row.filepath,
            )
        try:
            repo.delete(row.id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "retention delete failed for report %d",
                row.id,
            )


# Per-format implementations


def _check_cancel(
    token: CancellationToken,
    request: ReportRequest,
) -> None:
    if token.is_set():
        raise ReportCancelled(f"Report {request.report_id} cancelled before next step")


def _emit_step(
    sink: ReportEventSink,
    request: ReportRequest,
    step: str,
    progress: int,
    started: bool,
) -> None:
    if started:
        sink.emit(
            StepStarted(
                report_id=request.report_id,
                project_id=request.project_id,
                step=step,
                progress=progress,
                message=f"{step} started",
            )
        )
    else:
        sink.emit(
            StepCompleted(
                report_id=request.report_id,
                project_id=request.project_id,
                step=step,
                progress=progress,
                message=f"{step} completed",
            )
        )


def _run_text(
    request: ReportRequest,
    finding_repo: FindingRepositoryPort,
    sink: ReportEventSink,
    token: CancellationToken,
) -> Path:
    _check_cancel(token, request)

    _emit_step(sink, request, "aggregate", 0, started=True)
    generator = ReportGenerator(None, request.project, finding_repo)
    aggregated = generator._aggregate_findings()  # noqa: SLF001
    _emit_step(sink, request, "aggregate", 25, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "render", 25, started=True)
    fmt = request.format
    renderers: dict[str, Callable[[dict], str]] = {
        "markdown": generator._render_markdown,  # noqa: SLF001
        "html": generator._render_html,  # noqa: SLF001
        "json": generator._render_json,  # noqa: SLF001
    }
    content = renderers[fmt](aggregated)
    _emit_step(sink, request, "render", 75, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "write", 75, started=True)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    request.output_path.write_text(content, encoding="utf-8")
    _emit_step(sink, request, "write", 100, started=False)
    return request.output_path


def _run_pdf(
    request: ReportRequest,
    prompt: UserPromptPort,
    template_renderer: HtmlTemplateRenderer,
    pdf_renderer: PdfRenderer,
    finding_repo: FindingRepositoryPort,
    sink: ReportEventSink,
    token: CancellationToken,
) -> Path:
    from application.reporting import assembler as assembler_mod

    _check_cancel(token, request)
    assembler = assembler_mod.ReportAssembler(
        project=request.project,
        base_path=request.base_path,
        prompt=prompt,
        template_renderer=template_renderer,
        pdf_renderer=pdf_renderer,
        finding_repo=finding_repo,
        testing_type=request.testing_type,
        engagement_date=request.engagement_date,
        company_name_override=request.company_name_override,
        skip_triage=request.skip_triage,
    )

    _emit_step(sink, request, "build_context", 0, started=True)
    context = assembler.build_context()
    _emit_step(sink, request, "build_context", 33, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "render_pdf", 33, started=True)
    pdf_bytes = assembler.render_pdf(context)
    _emit_step(sink, request, "render_pdf", 75, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "write", 75, started=True)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    request.output_path.write_bytes(pdf_bytes)
    _emit_step(sink, request, "write", 100, started=False)
    return request.output_path
