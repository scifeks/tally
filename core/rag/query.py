"""Semantic search and RAG-augmented chat over a project's ChromaDB collection."""

import logging
import re
from typing import Any

import ollama

from core.config.manager import ConfigManager

from .engine import RAGEngine, verify_ollama_available

logger = logging.getLogger(__name__)

_DEFAULT_N_RESULTS = 20

_SYSTEM_PROMPT = """\
You are a penetration testing assistant analyzing security findings.
Use the provided context to answer questions about vulnerabilities,
hosts, services, and security issues found in scans.

Context:
{context}

Answer the user's question based on this context. If the context
doesn't contain relevant information, say so."""


class QueryEngine:
    """Semantic search and LLM chat over a project's ChromaDB collection."""

    def __init__(
        self,
        rag_engine: RAGEngine,
        llm_model: str | None = None,
        ollama_base_url: str | None = None,
    ) -> None:
        """Initialise the query engine.

        Args:
            rag_engine: Initialised RAGEngine for the current project.
            llm_model: Ollama chat model override; falls back to rag_engine default.
            ollama_base_url: Ollama API URL override; falls back to rag_engine default.
        """
        self._engine = rag_engine
        self.llm_model = llm_model or rag_engine.llm_model
        self.ollama_base_url = ollama_base_url or rag_engine.ollama_base_url

        # Load known tool names from commands.json at runtime — no hardcoded list.
        config_manager = ConfigManager(str(rag_engine.base_path))
        commands = config_manager.load_commands_config()
        self._known_tools: frozenset[str] = (
            frozenset(commands.keys()) if commands else frozenset()
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        n_results: int = _DEFAULT_N_RESULTS,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic search against the findings collection.

        When no explicit ``filters`` are provided, the query is inspected for
        a known tool name. If exactly one tool is matched, a metadata filter is
        applied automatically and ``n_results`` is set to the full count of
        documents for that tool so minority tools are never crowded out.

        Args:
            query:     Natural-language query string.
            n_results: Maximum number of results when no tool filter is active.
            filters:   Optional metadata filter dict (e.g. ``{"tool": "nmap"}``).
                       When provided, auto-detection is skipped.

        Returns:
            List of result dicts sorted by relevance (lowest distance first).
            Each dict has keys ``"document"`` (str), ``"metadata"`` (dict),
            and ``"distance"`` (float).
        """
        if not query.strip():
            return []

        collection = self._engine._collection
        if collection is None:
            return []

        total = self._engine.count_documents()
        if total == 0:
            return []

        # Auto-detect tool filter when none is explicitly provided.
        if filters is None:
            filters = self._detect_tool_filter(query)
            if filters:
                # Retrieve all documents for this tool so volume imbalance
                # cannot crowd them out of the result set.
                try:
                    id_result = collection.get(where=filters, include=[])
                    tool_count = len(id_result.get("ids") or [])
                except Exception:
                    tool_count = 0
                if tool_count > 0:
                    n_results = tool_count

        # ChromaDB errors if n_results > number of documents in the collection.
        n = min(n_results, total)

        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": n,
            "include": ["documents", "metadatas", "distances"],
        }
        if filters:
            kwargs["where"] = filters

        try:
            raw = collection.query(**kwargs)
        except Exception as exc:
            logger.warning("search query failed: %s", exc)
            return []

        docs = (raw.get("documents") or [[]])[0]
        metas = (raw.get("metadatas") or [[]])[0]
        dists = (raw.get("distances") or [[]])[0]

        results = []
        for doc, meta, dist in zip(docs, metas, dists):
            results.append({"document": doc, "metadata": meta or {}, "distance": dist})

        results.sort(key=lambda r: r["distance"])
        return results

    def chat(self, message: str, n_context: int = _DEFAULT_N_RESULTS) -> str:
        """RAG-augmented chat: retrieve context then query the LLM.

        Args:
            message:   User's question or message.
            n_context: Maximum context chunks for unfiltered queries. When a
                       tool filter is detected, all docs for that tool are used.

        Returns:
            LLM response string, or a user-facing error message string.
        """
        if not message.strip():
            return "Please provide a message."

        if not verify_ollama_available(self.ollama_base_url):
            return "Cannot connect to Ollama. Is it running? (ollama serve)"

        results = self.search(message, n_results=n_context)
        if not results:
            return "No relevant findings found for your query."

        context_lines = []
        for i, r in enumerate(results, 1):
            meta = r["metadata"]
            tool = meta.get("tool", "")
            finding_type = meta.get("finding_type", "")
            label = f"[{tool}/{finding_type}]" if tool else ""
            context_lines.append(f"{i}. {label} {r['document']}")
        context = "\n".join(context_lines)

        system_prompt = _SYSTEM_PROMPT.format(context=context)

        try:
            client = ollama.Client(host=self.ollama_base_url)
            response = client.chat(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                options={"temperature": 0.7, "num_predict": 2000},
            )
            # Support both attribute access (0.2.x+) and dict access (0.1.x)
            msg = (
                response.message
                if hasattr(response, "message")
                else response["message"]
            )
            content = msg.content if hasattr(msg, "content") else msg["content"]
            return content or ""
        except Exception as exc:
            logger.error("LLM chat failed: %s", exc)
            return f"LLM error: {exc}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_tool_filter(self, query: str) -> dict[str, Any] | None:
        """Detect a single tool name in ``query`` and return a ChromaDB filter.

        Scans the lowercased query for each known tool name using word-boundary
        matching. Returns a ``{"tool": name}`` filter if exactly one tool is
        found. Returns ``None`` for zero or multiple matches so that general
        queries ("summarize all findings") and multi-tool queries ("nmap and
        gitleaks") fall through to unfiltered retrieval.

        Args:
            query: The user's raw query string.

        Returns:
            A ChromaDB ``where`` dict, or ``None``.
        """
        q = query.lower()
        matched = [t for t in self._known_tools if re.search(rf"\b{re.escape(t)}\b", q)]
        if len(matched) == 1:
            return {"tool": matched[0]}
        return None
