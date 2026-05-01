"""Factory for the ChromaDB-backed VectorIndex."""

from __future__ import annotations

from pathlib import Path

from application.ports.embedding_provider import EmbeddingProvider
from application.ports.vector_index import VectorIndex
from core.project_paths import ProjectPaths
from infrastructure.vector.chromadb_adapter import ChromaDBVectorIndex


def make_chromadb_vector_index(
    project_name: str,
    base_path: Path,
    embedding_provider: EmbeddingProvider,
) -> VectorIndex:
    """Build a project-scoped VectorIndex backed by ChromaDB.

    Resolves the project's chroma directory through ProjectPaths, ensures it
    exists, and constructs the adapter with collection name
    ``f"findings_{project}"``.
    """
    if not project_name:
        raise ValueError("project_name must not be empty")

    paths = ProjectPaths.from_canonical(base_path, project_name)
    if not paths.root.exists():
        raise ValueError(
            f"Project directory does not exist: {paths.root}. Create the project first."
        )

    chroma_path = paths.chroma_db
    chroma_path.mkdir(parents=True, exist_ok=True)
    collection_name = f"findings_{project_name}"

    return ChromaDBVectorIndex(
        chroma_path=chroma_path,
        collection_name=collection_name,
        embedding_provider=embedding_provider,
        collection_metadata={
            "project": project_name,
            "hnsw:space": "cosine",
        },
    )
