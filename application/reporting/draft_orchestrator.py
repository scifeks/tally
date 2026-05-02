"""Hexagonal draft orchestrator (Phase 7.5).

Wraps the per-section LLM draft generation behind a single entry point
that:

- emits ``DraftEvent`` instances through a ``DraftEventSink`` port,
- honors a ``CancellationToken`` between steps,
- accepts a ``force_overwrite`` flag so the API can never block on stdin.

The orchestrator owns filesystem writes and DB lifecycle updates; the
caller (REPL loop or web runner) acquires the job lock and passes in
both the sink and the repository.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from application.locking.cancellation import CancellationToken
from application.ports.draft_event_sink import DraftEventSink, NullDraftEventSink
from application.rag.knowledge_base import FindingKnowledgeBase
from application.rag.query import QueryEngine
from application.reporting.blurbs import load_blurb
from application.reporting.draft_query import DraftQueryService
from application.reporting.drafts import SECTION_REGISTRY
from application.reporting.risk_level import compute_risk_level
from application.reporting.tal_id import assign_tal_ids_to_findings, resolve_prefix
from core.config.manager import ConfigManager
from core.project_paths import ProjectPaths
from domain.pipeline.report_events import DraftCompleted, DraftFailed, DraftStarted
from infrastructure.embedding.factory import get_embedding_provider
from infrastructure.llm.factory import get_llm_provider
from infrastructure.store import make_store
from infrastructure.store.connection import ConnectionFactory
from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.vector.factory import make_chromadb_vector_index

if TYPE_CHECKING:
    from application.ports.draft_repository import DraftRepositoryPort
    from application.ports.user_prompt import UserPromptPort
    from core.config.schemas import Repository
    from domain.findings.entry import Finding
    from domain.reports.entry import DraftRow


def _active_repos(base_path: str, project_name: str) -> list[Repository]:
    """Return active repos for the project, or ``[]`` if none."""
    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.findings_db.exists():
        return []
    factory = ConnectionFactory(paths.findings_db)
    factory.init_schema()
    return RepositoryRepository(factory).list_active()


logger = logging.getLogger(__name__)

_SECTION_RAG_N_RESULTS: dict[str, int] = {
    "executive-summary": 20,
    "risk-level": 20,
    "critical-issues": 20,
    "improvement-points": 20,
    "general-recommendations": 20,
}


class DraftCancelled(Exception):
    """Raised when cooperative cancellation is observed between steps."""


class DraftOverwriteDenied(Exception):
    """Raised when the draft file exists and force_overwrite is False."""


class DraftGenerationError(Exception):
    """Raised on non-retriable errors during draft generation."""


@dataclass(frozen=True)
class DraftRequest:
    project: str
    base_path: Path
    section: str
    force_overwrite: bool = False
    skip_triage: bool = False
    project_id: int | None = None


def run_draft(
    request: DraftRequest,
    *,
    prompt: UserPromptPort,
    repo: DraftRepositoryPort,
    event_sink: DraftEventSink | None = None,
    cancel_token: CancellationToken | None = None,
) -> Path:
    """Generate a draft for *request.section*. Returns the written file path.

    Emits ``DraftStarted`` before generation and ``DraftCompleted`` or
    ``DraftFailed`` on completion. ``DraftCancelled`` is raised (and
    ``DraftFailed`` emitted) on cooperative cancellation.
    ``DraftOverwriteDenied`` is raised (and ``DraftFailed`` emitted) when
    the file exists and ``force_overwrite`` is ``False``.
    """
    sink: DraftEventSink = event_sink or NullDraftEventSink()
    token = cancel_token or CancellationToken()

    section = request.section
    if section not in SECTION_REGISTRY:
        valid = ", ".join(SECTION_REGISTRY.keys())
        raise ValueError(f"Unknown section {section!r}. Valid: {valid}")

    paths = ProjectPaths.from_canonical(request.base_path, request.project)
    draft_dir = paths.reports_draft_dir
    draft_dir.mkdir(parents=True, exist_ok=True)

    draft_path = draft_dir / f"{section}.md"
    if draft_path.exists() and not request.force_overwrite:
        raise DraftOverwriteDenied(
            f"Draft already exists at {draft_path}. Use force=True to overwrite."
        )

    prior_row: DraftRow | None = repo.get(section)
    repo.upsert_generating(section)

    sink.emit(
        DraftStarted(
            report_id=0,
            project_id=request.project_id,
            section=section,
            message=f"Generating draft for {section}",
        )
    )

    try:
        output = _generate(request, section, draft_path, draft_dir, token, prompt)
    except Exception as exc:
        repo.restore(section, prior_row)
        sink.emit(
            DraftFailed(
                report_id=0,
                project_id=request.project_id,
                section=section,
                error=type(exc).__name__,
                message=str(exc),
            )
        )
        raise

    generated_at = datetime.now(UTC).isoformat()
    repo.mark_drafted(section, generated_at)

    content = output.read_text(encoding="utf-8")
    word_count = len(content.split())
    file_size = output.stat().st_size

    sink.emit(
        DraftCompleted(
            report_id=0,
            project_id=request.project_id,
            section=section,
            output_path=str(output),
            file_size_bytes=file_size,
            word_count=word_count,
            message=f"Draft saved to {output}",
        )
    )
    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_cancel(token: CancellationToken, section: str) -> None:
    if token.is_set():
        raise DraftCancelled(f"Draft generation for {section!r} cancelled")


def _generate(
    request: DraftRequest,
    section: str,
    draft_path: Path,
    draft_dir: Path,
    token: CancellationToken,
    prompt: UserPromptPort,
) -> Path:
    """Execute LLM generation steps and write the file. Returns the path."""
    del prompt  # accepted for interface parity with run_report; no interactive steps
    _check_cancel(token, section)

    llm = get_llm_provider("report", request.base_path)
    if not llm.is_available():
        raise DraftGenerationError(
            "LLM provider unavailable. Check config/global.json."
        )

    generator_cls = SECTION_REGISTRY[section]
    generator = generator_cls(llm, draft_dir)

    _check_cancel(token, section)
    _, finding_repo, _, _ = make_store(request.base_path, request.project)
    query = DraftQueryService(finding_repo)
    findings = query.get_filtered_findings(skip_triage=request.skip_triage)

    if not findings:
        msg = (
            "No findings in the database. Run a scan first."
            if request.skip_triage
            else (
                "No triaged findings with should_report=1. "
                "Run triage before generating drafts."
            )
        )
        raise DraftGenerationError(msg)

    sev_dist = query.severity_distribution(findings)
    conf_dist = query.confidence_distribution(findings)
    risk_counts = query.build_risk_counts(findings)
    risk_level = compute_risk_level(risk_counts)

    config = ConfigManager(str(request.base_path))
    project_cfg = config.load_project_config(request.project)
    project_name = project_cfg.project_name if project_cfg else request.project
    engagement_date = project_cfg.created[:10] if project_cfg else ""
    repos = [r.name for r in _active_repos(str(request.base_path), request.project)]
    prefix = resolve_prefix(
        project_cfg.abbreviation if project_cfg else "",
        config.global_config.report_finding_prefix,
    )
    findings = assign_tal_ids_to_findings(findings, prefix=prefix)

    context = _build_context(
        section=section,
        query=query,
        findings=findings,
        sev_dist=sev_dist,
        conf_dist=conf_dist,
        risk_counts=risk_counts,
        risk_level=risk_level,
        project_name=project_name,
        engagement_date=engagement_date,
        repos=repos,
        draft_dir=draft_dir,
        prefix=prefix,
    )

    _check_cancel(token, section)
    embedding_provider = get_embedding_provider(request.base_path)
    chat_provider = get_llm_provider("chat", request.base_path)
    vector_index = make_chromadb_vector_index(
        project_name=request.project,
        base_path=request.base_path,
        embedding_provider=embedding_provider,
    )
    kb = FindingKnowledgeBase(
        vector_index=vector_index,
        chat_provider=chat_provider,
        project_name=request.project,
        base_path=request.base_path,
    )
    query_engine = QueryEngine(kb)
    try:
        rag_query = _build_rag_query(section, context)
        if rag_query:
            try:
                n = _SECTION_RAG_N_RESULTS.get(section, 20)
                results = query_engine.search(rag_query, n_results=n)
                context["rag_context"] = "\n\n".join(
                    doc for r in results if (doc := r.get("document"))
                )
            except Exception as exc:
                logger.warning("ChromaDB query failed for %r: %s", section, exc)
                context["rag_context"] = ""
    finally:
        kb.close()

    _check_cancel(token, section)
    content = generator.generate(context)
    draft_path.write_text(content, encoding="utf-8")
    return draft_path


def _build_rag_query(section: str, context: dict[str, Any]) -> str | None:
    """Return a ChromaDB query string for *section*, or ``None`` to skip."""
    if section == "scope-and-methodology":
        return None

    if section == "executive-summary":
        return "critical and high severity vulnerabilities and security risks"

    if section == "risk-level":
        return "all security findings by severity and tool"

    if section == "critical-issues":
        findings: list[dict[str, Any]] = context.get("top_findings", [])
        terms: list[str] = []
        for field in ("vulnerability_id", "cwe", "risk_type"):
            seen: set[str] = set()
            for f in findings:
                val = f.get(field)
                if val and isinstance(val, str) and val not in seen:
                    seen.add(val)
                    terms.append(val)
                if len(seen) >= 5:
                    break
        base = "critical high severity vulnerabilities exploitable"
        return f"{base} {' '.join(terms)}" if terms else base

    if section == "improvement-points":
        groups: list[tuple[str, int]] = context.get("risk_type_groups", [])
        names = [rt for rt, _ in groups[:5] if rt and isinstance(rt, str)]
        base = "recurring patterns systemic weaknesses"
        return f"recurring {' '.join(names)} {base}" if names else base

    if section == "general-recommendations":
        groups = context.get("risk_type_groups", [])
        names = [rt for rt, _ in groups[:5] if rt and isinstance(rt, str)]
        base = "remediation steps fix recommendations"
        return f"{' '.join(names)} {base}" if names else base

    return None


def _build_context(
    section: str,
    query: DraftQueryService,
    findings: list[Finding],
    sev_dist: dict[str, int],
    conf_dist: dict[str, int],
    risk_counts: Any,
    risk_level: Any,
    project_name: str,
    engagement_date: str,
    repos: list[str],
    draft_dir: Path,
    prefix: str = "",
) -> dict[str, Any]:
    """Assemble the template context dict for *section*."""
    base: dict[str, Any] = {
        "project_name": project_name,
        "engagement_date": engagement_date,
        "repos": repos,
        "total": len(findings),
        "sev_dist": sev_dist,
        "conf_dist": conf_dist,
        "risk_counts": risk_counts,
        "risk_level": risk_level,
        "max_enumerate": 20,
        "finding_id_prefix": prefix,
    }

    if section in ("executive-summary", "risk-level"):
        return base

    if section == "critical-issues":
        base["top_findings"] = query.top_findings(findings, n=5)
        return base

    if section == "improvement-points":
        base["risk_type_groups"] = query.risk_type_groups(findings, top_n=8)
        return base

    if section == "scope-and-methodology":
        distinct_tools = query.distinct_tools(findings)
        base.update(
            {
                "tools": distinct_tools,
                "url_hosts": query.distinct_url_hosts(findings),
                "ecosystems": query.distinct_ecosystems(findings),
                "tools_blurb": _load_tools_blurb(distinct_tools),
            }
        )
        return base

    if section == "general-recommendations":
        base.update(
            {
                "risk_type_groups": query.risk_type_groups(findings, top_n=8),
                "recurring_by_risk_type": query.recurring_by_risk_type(findings),
                "improvement_points_draft": _load_existing_draft(
                    draft_dir, "improvement-points"
                ),
            }
        )
        return base

    return base


def _load_tools_blurb(tools: list[str]) -> str:
    tool_list = "\n".join(f"- {t}" for t in tools) if tools else "(no tools recorded)"
    try:
        return load_blurb("tools-used", {"tool_list": tool_list})
    except Exception as exc:
        logger.warning("Could not load tools-used blurb: %s", exc)
        return tool_list


def _load_existing_draft(draft_dir: Path, section: str) -> str | None:
    path = draft_dir / f"{section}.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read existing draft %r: %s", section, exc)
    return None
