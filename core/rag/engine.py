"""RAG engine foundation using ChromaDB for project-isolated vector storage."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.types import Documents, Embeddable, EmbeddingFunction, Embeddings

from core.config.manager import ConfigManager
from core.llm import LLMProvider, get_llm_provider
from core.llm.ollama_adapter import get_ollama_models as get_ollama_models  # re-export
from core.llm.ollama_adapter import (  # re-export
    verify_ollama_available as verify_ollama_available,
)

logger = logging.getLogger(__name__)


class _ProviderEmbeddingFn:
    """ChromaDB EmbeddingFunction wrapper that delegates to an LLMProvider."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        return [self._provider.embed(t) for t in input]  # type: ignore[return-value]

    def embed_query(self, input: Documents) -> Embeddings:  # noqa: A002  # ChromaDB query path
        return [self._provider.embed(t) for t in input]  # type: ignore[return-value]

    def name(self) -> str:  # ChromaDB EmbeddingFunction protocol
        return "default"


class RAGEngine:
    """Project-isolated RAG engine backed by ChromaDB and Ollama embeddings.

    Each project gets its own persistent ChromaDB directory under:
        <base_path>/projects/<project_name>/chroma_db/

    Collection name format: ``findings_<project_name>``

    Metadata schema stored per document:
        - tool (str)         – which tool generated the finding
        - profile (str)      – nmap profile / repo name (optional)
        - timestamp (str)    – ISO-8601 UTC
        - severity (str)     – low/medium/high/critical (optional)
        - finding_type (str) – vulnerability/informational/secret/dependency/etc.
        - source_file (str)  – path to raw output file
    """

    def __init__(
        self,
        project_name: str,
        base_path: str = ".",
        chat_provider: LLMProvider | None = None,
    ) -> None:
        """Initialise the RAG engine for a specific project.

        Args:
            project_name: Identifier for the current engagement project.
            base_path: Application root directory (contains projects/).
            chat_provider: LLMProvider override; resolved from config if None.

        Raises:
            ValueError: If project_name is empty or the resolved project directory
                        does not exist.
            RuntimeError: If ChromaDB or Ollama cannot be initialised.
        """
        if not project_name:
            raise ValueError("project_name must not be empty")

        self.project_name = project_name
        self.base_path = Path(base_path).resolve()

        self.chat_provider: LLMProvider = chat_provider or get_llm_provider(
            "chat", self.base_path
        )

        # Validate project directory
        self._project_dir = self.base_path / "projects" / project_name
        if not self._project_dir.exists():
            raise ValueError(
                f"Project directory does not exist: {self._project_dir}. "
                "Create the project first."
            )

        # Isolated ChromaDB path for this project
        self._chroma_path = self._project_dir / "chroma_db"
        self._chroma_path.mkdir(parents=True, exist_ok=True)

        self._collection_name = f"findings_{project_name}"

        self._client: ClientAPI | None = None
        self._collection: chromadb.Collection | None = None

        self._init_chromadb()
        self._init_sqlite()

        # Log the embedding model for observability
        config = ConfigManager(str(self.base_path)).global_config
        embedding_info = config.ollama.embedding_model if config.ollama else "unknown"
        logger.info(
            "RAGEngine ready — project=%s  chroma=%s  embedding=%s",
            project_name,
            self._chroma_path,
            embedding_info,
        )

    # ------------------------------------------------------------------
    # Internal initialisation
    # ------------------------------------------------------------------

    def _init_sqlite(self) -> None:
        """Initialise SQLite schema for this project (creates tables if absent)."""
        try:
            from core.store import SQLiteStore

            store = SQLiteStore(self.base_path, self.project_name)
            store._init_schema()
        except Exception as exc:
            logger.warning("SQLite schema init failed: %s", exc)

    def _build_chroma_client(self) -> ClientAPI:
        """Return a configured ChromaDB client (PersistentClient by default)."""
        return chromadb.PersistentClient(path=str(self._chroma_path))

    def _init_chromadb(self) -> None:
        """Create the ChromaDB persistent client and ensure the collection exists."""
        try:
            self._client = self._build_chroma_client()
        except Exception as exc:
            logger.error(
                "Failed to create ChromaDB client at %s: %s", self._chroma_path, exc
            )
            raise RuntimeError(
                "ChromaDB initialisation failed for project"
                f" '{self.project_name}': {exc}"
            ) from exc

        self._collection = self.get_or_create_collection()

    def _build_embedding_function(
        self,
    ) -> EmbeddingFunction[Embeddable]:
        """Return an embedding function backed by the chat provider.

        Raises:
            RuntimeError: If the provider is not reachable.
        """
        if not self.chat_provider.is_available():
            logger.error("LLM provider not reachable. Start Ollama with: ollama serve")
            raise RuntimeError(
                "LLM provider is not available. Please start it with: ollama serve"
            )

        return cast(
            EmbeddingFunction[Embeddable],
            _ProviderEmbeddingFn(self.chat_provider),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_or_create_collection(self) -> chromadb.Collection:
        """Return the project's ChromaDB collection, creating it if absent.

        Returns:
            The ChromaDB Collection object.

        Raises:
            RuntimeError: If the collection cannot be created.
        """
        if self._client is None:
            raise RuntimeError("ChromaDB client is not initialised")

        embedding_fn: EmbeddingFunction[Embeddable] = self._build_embedding_function()

        try:
            collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=embedding_fn,
                metadata={"project": self.project_name, "hnsw:space": "cosine"},
            )
            logger.debug(
                "Collection '%s' ready (%d docs)",
                self._collection_name,
                collection.count(),
            )
            return collection
        except Exception as exc:
            logger.error(
                "Failed to get/create collection '%s': %s", self._collection_name, exc
            )
            raise RuntimeError(
                f"Could not create ChromaDB collection '{self._collection_name}': {exc}"
            ) from exc

    def count_documents(self) -> int:
        """Return the total number of documents stored in this project's collection.

        Returns:
            Document count (0 if collection is empty or uninitialised).
        """
        if self._collection is None:
            return 0
        try:
            return self._collection.count()
        except Exception as exc:
            logger.warning("count_documents failed: %s", exc)
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Return statistics for the project's vector store.

        Returns:
            Dict with keys:
                - total_documents (int)
                - by_tool (Dict[str, int])   – document counts keyed by tool name
                - by_severity (Dict[str, int]) – counts by severity level
                - last_updated (Optional[str]) – ISO timestamp of the most recent doc
        """
        stats: dict[str, Any] = {
            "total_documents": 0,
            "by_tool": {},
            "by_severity": {},
            "last_updated": None,
        }

        if self._collection is None:
            return stats

        total = self.count_documents()
        stats["total_documents"] = total

        if total == 0:
            return stats

        try:
            result = self._collection.get(include=["metadatas"])
            metadatas: list[dict[str, Any]] = result.get("metadatas") or []  # type: ignore[assignment]

            by_tool: dict[str, int] = {}
            by_severity: dict[str, int] = {}
            latest_ts: str | None = None

            for meta in metadatas:
                tool = meta.get("tool", "unknown")
                by_tool[tool] = by_tool.get(tool, 0) + 1

                severity = meta.get("severity")
                if severity:
                    by_severity[severity] = by_severity.get(severity, 0) + 1

                ts = meta.get("timestamp")
                if ts and (latest_ts is None or ts > latest_ts):
                    latest_ts = ts

            stats["by_tool"] = by_tool
            stats["by_severity"] = by_severity
            stats["last_updated"] = latest_ts
        except Exception as exc:
            logger.warning("get_stats metadata fetch failed: %s", exc)

        return stats

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def delete_findings(
        self,
        tool: str | None = None,
        profile: str | None = None,
    ) -> int:
        """Delete stored findings, optionally filtered by tool and/or profile.

        Args:
            tool:    Tool name (e.g. ``"nmap"``). If ``None``, all findings are
                     deleted (only valid when ``profile`` is also ``None``).
            profile: Profile name to scope the deletion. If ``None``, all
                     findings for the tool are deleted regardless of profile.
                     Requires ``tool`` to be set.

        Returns:
            Number of documents deleted (0 if collection is uninitialised or
                     no matching documents exist).

        Raises:
            ValueError: If ``profile`` is given without ``tool``.
        """
        if profile is not None and tool is None:
            raise ValueError("--profile requires --tool to be specified")

        if self._collection is None:
            return 0

        if tool is not None and profile is not None:
            where: dict[str, Any] = {"$and": [{"tool": tool}, {"profile": profile}]}
        elif tool is not None:
            where = {"tool": tool}
        else:
            where = {}

        try:
            kwargs: dict[str, Any] = {"include": []}
            if where:
                kwargs["where"] = where
            result = self._collection.get(**kwargs)
            ids: list[str] = result.get("ids") or []
            if ids:
                self._collection.delete(ids=ids)
            return len(ids)
        except Exception as exc:
            logger.warning(
                "delete_findings failed (tool=%s profile=%s): %s", tool, profile, exc
            )
            return 0

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Upsert documents into the project's collection.

        Uses ChromaDB ``upsert`` so existing IDs are updated rather than
        causing a duplicate-key error.

        Args:
            texts:     Document text strings.
            metadatas: Parallel list of metadata dicts.
            ids:       Stable unique IDs for deduplication.

        Raises:
            RuntimeError: If the collection is not initialised or ChromaDB
                          raises an error.
        """
        if self._collection is None:
            raise RuntimeError("ChromaDB collection is not initialised")

        try:
            self._collection.upsert(documents=texts, metadatas=metadatas, ids=ids)  # type: ignore[arg-type]
            logger.debug(
                "Upserted %d documents into '%s'", len(ids), self._collection_name
            )
        except Exception as exc:
            logger.error("add_documents failed: %s", exc)
            raise RuntimeError(f"Failed to add documents to collection: {exc}") from exc

    def get_document_by_id(self, doc_id: str) -> dict | None:
        """Fetch a single document and its metadata by ID.

        Returns:
            Dict with keys ``id``, ``document``, ``metadata``, or ``None`` if
            not found.
        """
        assert self._collection is not None
        result = self._collection.get(ids=[doc_id], include=["documents", "metadatas"])
        if not result["ids"]:
            return None
        return {
            "id": result["ids"][0],
            "document": (result["documents"] or [""])[0],
            "metadata": (result["metadatas"] or [{}])[0],
        }

    def close(self) -> None:
        """Release ChromaDB file handles held by this engine instance."""
        if self._client is not None and hasattr(self._client, "close"):
            try:
                self._client.close()  # type: ignore[union-attr]
            except Exception:
                pass
        self._client = None
        self._collection = None

    def update_metadata(self, doc_id: str, metadata_updates: dict) -> None:
        """Merge metadata_updates into an existing document's metadata.

        Does NOT re-embed or change the document text. Existing fields not present
        in ``metadata_updates`` are preserved.

        Raises:
            ValueError: If ``doc_id`` is not found in the collection.
        """
        assert self._collection is not None
        existing = self._collection.get(ids=[doc_id], include=["metadatas"])
        if not existing["ids"]:
            raise ValueError(f"Document {doc_id!r} not found in collection")
        current_meta: dict = dict((existing["metadatas"] or [{}])[0])
        merged = {**current_meta, **metadata_updates}
        self._collection.update(ids=[doc_id], metadatas=[merged])

    @staticmethod
    def now_iso() -> str:
        """Return the current UTC time as an ISO-8601 string."""
        return datetime.now(UTC).isoformat()

    @property
    def collection_name(self) -> str:
        """ChromaDB collection name for this project."""
        return self._collection_name

    @property
    def chroma_path(self) -> Path:
        """Filesystem path to this project's ChromaDB directory."""
        return self._chroma_path
