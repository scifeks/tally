"""Pipeline handlers: IngestHandler (and BaseHandler with shared ChromaDB logic)."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from application.pipeline.fingerprint import compute_fingerprint
from application.rag.ingestor import (
    ToolHandlerFactory,
    filter_code_rows,
)
from application.rag.knowledge_base import FindingKnowledgeBase
from domain.findings.normalization import (
    NormalizedFinding,
    normalise_finding_for_insert,
    prepare_row_for_render,
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
    """Shared FindingKnowledgeBase cache for ChromaDB persistence."""

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

    def _persist_to_chromadb(
        self, ids: list[int], project_name: str, base_path: str
    ) -> None:
        """Write findings to ChromaDB by their SQLite IDs."""
        from application.pipeline.chromadb_ids import chromadb_doc_id

        try:
            kb = self._get_knowledge_base(project_name, base_path)
        except Exception as exc:
            logger.warning(
                "%s: knowledge base init failed: %s",
                type(self).__name__,
                exc,
            )
            return

        try:
            rows = self._finding_repo.get_by_ids(ids)
            grouped: defaultdict[tuple[str, str], list[dict]] = defaultdict(list)
            for row in rows:
                grouped[(row["tool"], row["profile"])].append(row)
            for (tool, profile), group_rows in grouped.items():
                handler = ToolHandlerFactory.load(tool)
                if handler is None:
                    continue
                texts = [
                    f"Repository: {profile} | "
                    f"{handler.render(prepare_row_for_render(row))}"
                    for row in group_rows
                ]
                metadatas: list[Mapping[str, Any]] = [
                    {
                        "tool": tool,
                        "profile": profile,
                        "run_id": row.get("run_id", 0),
                        "severity": row.get("severity", ""),
                        "segment": row.get("segment", ""),
                        "status": row.get("status", "active"),
                        "fingerprint": row.get("fingerprint", ""),
                    }
                    for row in group_rows
                ]
                doc_ids = [
                    chromadb_doc_id(row.get("fingerprint", ""), profile)
                    for row in group_rows
                ]
                seen: dict[str, int] = {}
                for i, doc_id in enumerate(doc_ids):
                    seen[doc_id] = i
                if len(seen) < len(doc_ids):
                    unique = sorted(seen.values())
                    doc_ids = [doc_ids[i] for i in unique]
                    texts = [texts[i] for i in unique]
                    metadatas = [metadatas[i] for i in unique]
                kb.add_findings(
                    documents=texts,
                    metadatas=metadatas,
                    ids=doc_ids,
                )
        except Exception as exc:
            logger.error(
                "%s: ChromaDB write error: %s",
                type(self).__name__,
                exc,
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
