"""Per-project FindingKnowledgeBase cache lookup."""

from __future__ import annotations

import logging
from pathlib import Path

from application.rag.knowledge_base import FindingKnowledgeBase
from infrastructure.embedding.factory import get_embedding_provider
from infrastructure.llm.factory import get_llm_provider
from infrastructure.vector.factory import make_chromadb_vector_index

logger = logging.getLogger(__name__)


def get_or_build_knowledge_base(
    cache: dict[str, FindingKnowledgeBase | None],
    project_name: str,
    base_path: str,
) -> FindingKnowledgeBase | None:
    """Lookup-or-build a FindingKnowledgeBase for *project_name*.

    Returns ``None`` (and caches the ``None``) if the embedding provider,
    LLM provider, or vector index cannot be constructed. Callers must
    handle ``None`` as "RAG unavailable for this project".
    """
    if project_name in cache:
        return cache[project_name]
    base = Path(base_path)
    try:
        embedding_provider = get_embedding_provider(base)
        chat_provider = get_llm_provider("chat", base)
        vector_index = make_chromadb_vector_index(
            project_name=project_name,
            base_path=base,
            embedding_provider=embedding_provider,
        )
        kb: FindingKnowledgeBase | None = FindingKnowledgeBase(
            vector_index=vector_index,
            chat_provider=chat_provider,
            project_name=project_name,
            base_path=base,
        )
    except (RuntimeError, OSError, ImportError) as exc:
        logger.warning(
            "knowledge base init failed for %s; Chroma sync disabled: %s",
            project_name,
            exc,
        )
        kb = None
    cache[project_name] = kb
    return kb
