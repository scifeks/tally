"""Pipeline handlers: IngestHandler and BaseHandler (shared KB cache)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from application.pipeline.fingerprint import compute_fingerprint
from application.rag.ingestor import (
    ToolHandlerFactory,
    filter_code_rows,
)
from application.rag.knowledge_base import FindingKnowledgeBase
from domain.findings.normalization import (
    NormalizedFinding,
    normalise_finding_for_insert,
)
from domain.pipeline.events import (
    EventBus,
    IngestCompleted,
    ToolCompleted,
)
from factories.llm import (
    create_embedding_provider,
    create_llm_provider,
    create_vector_index,
)

if TYPE_CHECKING:
    from pathlib import Path

    from application.ports.finding_repository import (
        FindingRepositoryPort,
    )
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )


logger = logging.getLogger(__name__)


def _build_knowledge_base(project_name: str, base_path: Path) -> FindingKnowledgeBase:
    embedding_provider = create_embedding_provider(base_path)
    logger.info(
        "Embedding provider: %s model=%s url=%s",
        type(embedding_provider).__name__,
        getattr(embedding_provider, "_model", "?"),
        getattr(embedding_provider, "_base_url", "?"),
    )
    chat_provider = create_llm_provider("chat", base_path)
    vector_index = create_vector_index(
        project_name=project_name,
        base_path=base_path,
        embedding_provider=embedding_provider,
    )
    return FindingKnowledgeBase(
        vector_index=vector_index,
        chat_provider=chat_provider,
        project_name=project_name,
        base_path=base_path,
    )


class BaseHandler:
    """Shared per-project knowledge-base cache for vector-index-backed strategies."""

    def __init__(self, finding_repo: FindingRepositoryPort) -> None:
        self._finding_repo = finding_repo
        self._knowledge_bases: dict[str, FindingKnowledgeBase] = {}

    def _get_knowledge_base(
        self, project_name: str, base_path: str
    ) -> FindingKnowledgeBase:
        from pathlib import Path

        key = f"{project_name}:{base_path}"
        if key not in self._knowledge_bases:
            self._knowledge_bases[key] = _build_knowledge_base(
                project_name, Path(base_path)
            )
        return self._knowledge_bases[key]

    def close(self) -> None:
        """Close all cached knowledge bases."""
        for kb in self._knowledge_bases.values():
            try:
                kb.close()
            except Exception:
                logger.exception(
                    "error closing knowledge base for %s",
                    getattr(kb, "_project_name", "unknown"),
                )


class IngestHandler(BaseHandler):
    """Handles ToolCompleted: normalizes findings to SQLite, emits IngestCompleted."""

    def __init__(
        self,
        bus: EventBus,
        finding_repo: FindingRepositoryPort,
        repo_repo: ProjectRepoRepositoryPort,
    ) -> None:
        super().__init__(finding_repo=finding_repo)
        self._bus = bus
        self._repo_repo = repo_repo

    def _resolve_repo_id(self, repo_name: str) -> int | None:
        if self._repo_repo is None:
            return None
        try:
            return self._repo_repo.find_id_by_name(repo_name)
        except Exception:
            return None

    def handle(self, event: ToolCompleted) -> None:
        result = event.result
        if (
            not result.success
            or not result.parsed_data
            or "error" in result.parsed_data
        ):
            self._bus.dispatch(
                IngestCompleted(
                    ids=[],
                    failed_tools=[],
                    run_id=event.run_id,
                    project_name=event.project_name,
                    base_path=event.base_path,
                )
            )
            return

        sqlite_ids: list[int] = []
        failed_tools: list[str] = []
        try:
            handler = ToolHandlerFactory.load(result.tool_name)
            if handler is None:
                self._bus.dispatch(
                    IngestCompleted(
                        ids=[],
                        failed_tools=[],
                        run_id=event.run_id,
                        project_name=event.project_name,
                        base_path=event.base_path,
                    )
                )
                return

            rows: list[dict] = handler.normalize(result, event.profile)

            if handler.domain == "code":
                if handler.segment in ("sca", "web"):
                    if event.repo:
                        repo_id = self._resolve_repo_id(event.repo)
                        for row in rows:
                            row.setdefault("repo", event.repo)
                            if repo_id is not None:
                                row.setdefault("repo_id", repo_id)
                else:
                    try:
                        active = self._repo_repo.list_active()
                    except Exception:
                        active = None
                    rows = filter_code_rows(
                        rows,
                        active,
                        event.repo,
                        result.tool_name,
                    )
            else:
                if event.repo:
                    repo_id = self._resolve_repo_id(event.repo)
                    for row in rows:
                        row.setdefault("repo", event.repo)
                        if repo_id is not None:
                            row.setdefault("repo_id", repo_id)

            normalized = []
            for r in rows:
                n = normalise_finding_for_insert(r)
                normalized.append(
                    NormalizedFinding(n.columns, n.meta, compute_fingerprint(r))
                )
            self._finding_repo.insert_findings(event.run_id or 0, normalized)
            fingerprints = [compute_fingerprint(row) for row in rows]
            sqlite_ids = self._finding_repo.get_ids_by_fingerprints(
                fingerprints, run_id=event.run_id or 0
            )
        except Exception as exc:
            logger.error(
                "IngestHandler: ingestion failed for %s: %s",
                result.tool_name,
                exc,
            )
            failed_tools.append(result.tool_name)

        self._bus.dispatch(
            IngestCompleted(
                ids=sqlite_ids,
                failed_tools=failed_tools,
                run_id=event.run_id,
                project_name=event.project_name,
                base_path=event.base_path,
            )
        )
