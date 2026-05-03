"""Per-request composer for the chat streaming inputs.

Resolves the project, looks up its knowledge base, builds the per-turn
``QueryEngine``, and acquires the chat ``LLMProvider``. The route
calls ``ChatStreamComposer.for_project(...)`` and reads ready-to-use
objects off the returned instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self

from application.chat.service import ProjectNotFound
from application.rag.knowledge_base_cache import get_or_build_knowledge_base
from application.rag.query import QueryEngine
from infrastructure.llm.factory import get_llm_provider

if TYPE_CHECKING:
    from application.ports.llm_provider import LLMProvider
    from application.project.registry_service import ProjectRegistryService
    from application.rag.knowledge_base import FindingKnowledgeBase


class RagUnavailable(RuntimeError):
    """Raised when the per-project knowledge base cannot be built."""


class ChatStreamComposer:
    """Holds the ``QueryEngine`` + ``LLMProvider`` pair for one chat turn."""

    def __init__(
        self,
        query_engine: QueryEngine,
        provider: LLMProvider,
        model_name: str,
    ) -> None:
        self._query_engine = query_engine
        self._provider = provider
        self._model_name = model_name

    @classmethod
    def for_project(
        cls,
        registry: ProjectRegistryService,
        knowledge_base_cache: dict[str, FindingKnowledgeBase | None],
        base_path: str,
        project_id: int,
    ) -> Self:
        row = registry.resolve_by_id(project_id)
        if row is None or row.archived_at:
            raise ProjectNotFound(f"project {project_id} not found")
        knowledge_base = get_or_build_knowledge_base(
            knowledge_base_cache, row.name, base_path
        )
        if knowledge_base is None:
            raise RagUnavailable(
                "RAG engine unavailable for this project; "
                "ChromaDB or embedding provider is not reachable"
            )
        provider = get_llm_provider("chat", base_path)
        return cls(
            query_engine=QueryEngine(knowledge_base),
            provider=provider,
            model_name=provider.model,
        )

    @property
    def query_engine(self) -> QueryEngine:
        return self._query_engine

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._model_name
