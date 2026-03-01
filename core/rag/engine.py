"""RAG engine foundation using ChromaDB for project-isolated vector storage."""
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction

from core.config.manager import ConfigManager

logger = logging.getLogger(__name__)


def verify_ollama_available(base_url: str) -> bool:
    """Check if Ollama is reachable at the given base URL.

    Args:
        base_url: Ollama API base URL, e.g. "http://localhost:11434"

    Returns:
        True if Ollama responds, False otherwise
    """
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def get_ollama_models(base_url: str) -> List[str]:
    """List models available in Ollama.

    Args:
        base_url: Ollama API base URL

    Returns:
        List of model name strings; empty list if Ollama is unreachable
    """
    import json

    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return []


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
        - finding_type (str) – vulnerability/host/port/secret/etc.
        - source_file (str)  – path to raw output file
    """

    def __init__(
        self,
        project_name: str,
        base_path: str = ".",
        llm_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
    ) -> None:
        """Initialise the RAG engine for a specific project.

        Args:
            project_name:    Identifier for the current engagement project.
            base_path:       Application root directory (contains projects/).
            llm_model:       Ollama chat model override; falls back to global config.
            embedding_model: Ollama embedding model override; falls back to global config.
            ollama_base_url: Ollama API URL override; falls back to global config.

        Raises:
            ValueError: If project_name is empty or the resolved project directory
                        does not exist.
            RuntimeError: If ChromaDB or Ollama cannot be initialised.
        """
        if not project_name:
            raise ValueError("project_name must not be empty")

        self.project_name = project_name
        self.base_path = Path(base_path).resolve()

        # Load defaults from global config
        config_manager = ConfigManager(str(self.base_path))
        global_config = config_manager.global_config

        self.llm_model = llm_model or global_config.default_llm
        self.embedding_model = embedding_model or global_config.default_embedding
        self.ollama_base_url = ollama_base_url or global_config.ollama_base_url

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

        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None

        self._init_chromadb()

        logger.info(
            "RAGEngine ready — project=%s  chroma=%s  embedding=%s",
            project_name,
            self._chroma_path,
            self.embedding_model,
        )

    # ------------------------------------------------------------------
    # Internal initialisation
    # ------------------------------------------------------------------

    def _init_chromadb(self) -> None:
        """Create the ChromaDB persistent client and ensure the collection exists."""
        try:
            self._client = chromadb.PersistentClient(path=str(self._chroma_path))
        except Exception as exc:
            logger.error("Failed to create ChromaDB client at %s: %s", self._chroma_path, exc)
            raise RuntimeError(
                f"ChromaDB initialisation failed for project '{self.project_name}': {exc}"
            ) from exc

        self._collection = self.get_or_create_collection()

    def _build_embedding_function(self) -> OllamaEmbeddingFunction:
        """Return a configured Ollama embedding function.

        Raises:
            RuntimeError: If Ollama is not reachable.
        """
        if not verify_ollama_available(self.ollama_base_url):
            logger.error(
                "Ollama not reachable at %s. Start Ollama with: ollama serve",
                self.ollama_base_url,
            )
            raise RuntimeError(
                f"Ollama is not running at {self.ollama_base_url}. "
                "Please start it with: ollama serve"
            )

        return OllamaEmbeddingFunction(
            url=f"{self.ollama_base_url}/api/embeddings",
            model_name=self.embedding_model,
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

        embedding_fn = self._build_embedding_function()

        try:
            collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=embedding_fn,
                metadata={"project": self.project_name, "hnsw:space": "cosine"},
            )
            logger.debug("Collection '%s' ready (%d docs)", self._collection_name, collection.count())
            return collection
        except Exception as exc:
            logger.error("Failed to get/create collection '%s': %s", self._collection_name, exc)
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

    def get_stats(self) -> Dict[str, Any]:
        """Return statistics for the project's vector store.

        Returns:
            Dict with keys:
                - total_documents (int)
                - by_tool (Dict[str, int])   – document counts keyed by tool name
                - by_severity (Dict[str, int]) – counts by severity level
                - last_updated (Optional[str]) – ISO timestamp of the most recent doc
        """
        stats: Dict[str, Any] = {
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
            metadatas: List[Dict[str, Any]] = result.get("metadatas") or []

            by_tool: Dict[str, int] = {}
            by_severity: Dict[str, int] = {}
            latest_ts: Optional[str] = None

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

    @staticmethod
    def now_iso() -> str:
        """Return the current UTC time as an ISO-8601 string."""
        return datetime.now(timezone.utc).isoformat()

    @property
    def collection_name(self) -> str:
        """ChromaDB collection name for this project."""
        return self._collection_name

    @property
    def chroma_path(self) -> Path:
        """Filesystem path to this project's ChromaDB directory."""
        return self._chroma_path
