"""Factory functions for LLM, embedding, and vector index construction."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from application.ports.embedding_provider import EmbeddingProvider
    from application.ports.llm_provider import LLMProvider
    from application.ports.vector_index import VectorIndex


def create_llm_provider(
    role: Literal["chat", "enrichment", "report"],
    base_path: str | Path,
) -> LLMProvider:
    from infrastructure.llm.factory import get_llm_provider

    return get_llm_provider(role, base_path)


def create_embedding_provider(
    base_path: str | Path,
) -> EmbeddingProvider:
    from infrastructure.embedding.factory import (
        get_embedding_provider,
    )

    return get_embedding_provider(base_path)


def create_vector_index(
    project_name: str,
    base_path: Path,
    embedding_provider: EmbeddingProvider,
    collection_type: str = "findings",
) -> VectorIndex:
    from infrastructure.vector.factory import (
        make_chromadb_vector_index,
    )

    return make_chromadb_vector_index(
        project_name=project_name,
        base_path=base_path,
        embedding_provider=embedding_provider,
        collection_type=collection_type,
    )
