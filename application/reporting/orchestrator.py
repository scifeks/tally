"""Hexagonal report orchestrator (Phase 7.4).

Wraps ``ReportGenerator`` (markdown/html/json) and ``ReportAssembler``
(pdf) behind a single entry point that:

- emits ``ReportEvent`` instances through a ``ReportEventSink`` port,
- honors a ``CancellationToken`` between steps,
- accepts a ``force_overwrite`` flag in lieu of the REPL's bare
  ``input()`` prompt (the API can never block on stdin).

The orchestrator does not touch the database or filesystem layout —
the caller (REPL command or web runner) decides where to write the
artifact and what row to update.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from application.locking.cancellation import CancellationToken
from application.ports.report_event_sink import (
    NullReportEventSink,
    ReportEventSink,
)
from application.ports.user_prompt import UserPromptPort
from application.reporting.generator import ReportGenerator
from application.reporting.pdf import PDFRenderError
from application.reporting.resolver import SectionMissingError
from domain.pipeline.report_events import (
    GenerationCancelled,
    GenerationCompleted,
    GenerationFailed,
    GenerationStarted,
    StepCompleted,
    StepStarted,
)
from infrastructure.store import make_store

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


def run_report(
    request: ReportRequest,
    *,
    prompt: UserPromptPort,
    event_sink: ReportEventSink | None = None,
    cancel_token: CancellationToken | None = None,
) -> Path:
    """Generate a report per *request*. Returns the final on-disk path.

    Steps emit events via *event_sink*. ``ReportCancelled`` is raised on
    cooperative cancellation between steps; ``ReportOverwriteDenied`` is
    raised when the file exists and ``force_overwrite`` is False.
    """
    sink: ReportEventSink = event_sink or NullReportEventSink()
    token = cancel_token or CancellationToken()

    fmt = request.format
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"Unknown format: {fmt!r}. Use one of {SUPPORTED_FORMATS}.")

    if request.output_path.exists() and not request.force_overwrite:
        raise ReportOverwriteDenied(f"Report already exists at {request.output_path}")

    sink.emit(
        GenerationStarted(
            report_id=request.report_id,
            project_id=request.project_id,
            format=fmt,
            message=f"Generating {fmt} report",
        )
    )

    try:
        if fmt == "pdf":
            output = _run_pdf(request, prompt, sink, token)
        else:
            output = _run_text(request, sink, token)
    except ReportCancelled:
        sink.emit(
            GenerationCancelled(
                report_id=request.report_id,
                project_id=request.project_id,
                message="Report generation cancelled",
            )
        )
        raise
    except (SectionMissingError, PDFRenderError, ReportOverwriteDenied) as exc:
        sink.emit(
            GenerationFailed(
                report_id=request.report_id,
                project_id=request.project_id,
                error=type(exc).__name__,
                message=str(exc),
            )
        )
        raise
    except Exception as exc:  # noqa: BLE001 — convert to event then re-raise
        sink.emit(
            GenerationFailed(
                report_id=request.report_id,
                project_id=request.project_id,
                error=type(exc).__name__,
                message=str(exc),
            )
        )
        raise

    size = output.stat().st_size if output.exists() else 0
    sink.emit(
        GenerationCompleted(
            report_id=request.report_id,
            project_id=request.project_id,
            output_path=str(output),
            file_size_bytes=size,
            message=f"Report saved to {output}",
        )
    )
    return output


# ---------------------------------------------------------------------------
# Per-format implementations
# ---------------------------------------------------------------------------


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
    sink: ReportEventSink,
    token: CancellationToken,
) -> Path:
    _check_cancel(token, request)
    _, finding_repo, _, _ = make_store(str(request.base_path), request.project)

    _emit_step(sink, request, "aggregate", 25, started=True)
    generator = ReportGenerator(None, request.project, finding_repo)
    aggregated = generator._aggregate_findings()  # noqa: SLF001
    _emit_step(sink, request, "aggregate", 25, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "render", 75, started=True)
    fmt = request.format
    renderers: dict[str, Callable[[dict], str]] = {
        "markdown": generator._render_markdown,  # noqa: SLF001
        "html": generator._render_html,  # noqa: SLF001
        "json": generator._render_json,  # noqa: SLF001
    }
    content = renderers[fmt](aggregated)
    _emit_step(sink, request, "render", 75, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "write", 100, started=True)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    request.output_path.write_text(content, encoding="utf-8")
    _emit_step(sink, request, "write", 100, started=False)
    return request.output_path


def _run_pdf(
    request: ReportRequest,
    prompt: UserPromptPort,
    sink: ReportEventSink,
    token: CancellationToken,
) -> Path:
    # Lazy import — tests patch ``application.reporting.assembler.ReportAssembler``
    # at the source module, so the orchestrator must resolve it at call time.
    from application.reporting import assembler as assembler_mod

    _check_cancel(token, request)
    assembler = assembler_mod.ReportAssembler(
        project=request.project,
        base_path=request.base_path,
        prompt=prompt,
        testing_type=request.testing_type,
        engagement_date=request.engagement_date,
        company_name_override=request.company_name_override,
        skip_triage=request.skip_triage,
    )

    _emit_step(sink, request, "build_context", 33, started=True)
    context = assembler.build_context()
    _emit_step(sink, request, "build_context", 33, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "render_pdf", 75, started=True)
    pdf_bytes = assembler.render_pdf(context)
    _emit_step(sink, request, "render_pdf", 75, started=False)

    _check_cancel(token, request)
    _emit_step(sink, request, "write", 100, started=True)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    request.output_path.write_bytes(pdf_bytes)
    _emit_step(sink, request, "write", 100, started=False)
    return request.output_path
