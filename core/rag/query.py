"""Semantic search and RAG-augmented chat over a project's ChromaDB collection."""

from __future__ import annotations

import logging
from typing import Any

from core.config.manager import ConfigManager
from core.llm import LLMProvider

from .engine import RAGEngine
from .search_parser import SearchQuery, parse_search_query

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
        llm_provider: LLMProvider | None = None,
    ) -> None:
        """Initialise the query engine.

        Args:
            rag_engine:   Initialised RAGEngine for the current project.
            llm_provider: LLMProvider override; falls back to the engine's
                          chat_provider if None.
        """
        self._engine = rag_engine
        self._provider: LLMProvider = llm_provider or rag_engine.chat_provider

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
        raw_input: str = "",
        n_results: int = _DEFAULT_N_RESULTS,
        query: SearchQuery | None = None,
    ) -> list[dict[str, Any]]:
        """Run semantic or metadata-only search, return results.

        Each result dict has keys: 'document' (str), 'metadata' (dict),
        'distance' (float | None). Distance is None for metadata-only searches.

        When query is provided it bypasses parse_search_query entirely.
        The n_results parameter is used by chat() to override the page size for
        context retrieval. When called from cmd_search, n_results is the default
        and pagination is driven by the SearchQuery object.

        Raises:
            SearchValidationError: Propagated to caller for user-friendly display.
        """
        if query is None:
            if not raw_input.strip():
                return []
            query = parse_search_query(raw_input, self._known_tools)

        total = self._engine.count_documents()
        if total == 0:
            return []

        # chat() passes n_results to override page_size for context retrieval
        page_size = n_results if n_results != _DEFAULT_N_RESULTS else query.page_size
        page = query.page
        offset = (page - 1) * page_size

        if query.is_semantic:
            # ChromaDB query has no native offset — fetch page*page_size, then slice.
            fetch_n = min(page_size * page, total)
            kwargs: dict[str, Any] = {
                "query_texts": [query.semantic_text],
                "n_results": fetch_n,
                "include": ["documents", "metadatas", "distances"],
            }
            if query.where_filter:
                kwargs["where"] = query.where_filter
            raw = self._engine.query_collection(**kwargs)
            docs = (raw.get("documents") or [[]])[0]
            metas = (raw.get("metadatas") or [[]])[0]
            dists = (raw.get("distances") or [[]])[0]
            all_results = [
                {"document": doc, "metadata": meta or {}, "distance": dist}
                for doc, meta, dist in zip(docs, metas, dists)
            ]
            all_results.sort(key=lambda r: r["distance"])
            return all_results[offset : offset + page_size]
        else:
            # Metadata-only — use collection.get() with native limit+offset.
            kwargs_get: dict[str, Any] = {
                "include": ["documents", "metadatas"],
                "limit": min(page_size, total),
                "offset": offset,
            }
            if query.where_filter:
                kwargs_get["where"] = query.where_filter
            raw_get = self._engine.get_documents(**kwargs_get)
            docs_g = raw_get.get("documents") or []
            metas_g = raw_get.get("metadatas") or []
            return [
                {"document": doc, "metadata": meta or {}, "distance": None}
                for doc, meta in zip(docs_g, metas_g)
            ]

    def chat(self, message: str, n_context: int = _DEFAULT_N_RESULTS) -> str:
        """RAG-augmented chat: retrieve context then query the LLM.

        Args:
            message:   User's question or message.
            n_context: Maximum context chunks for unfiltered queries. When a
                       tool filter is detected, all docs for that tool are used.

        Returns:
            LLM response string.
        """
        if not message.strip():
            return "Please provide a message."

        if not self._provider.is_available():
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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]
        return self._provider.chat(messages, temperature=0.7, num_predict=2000)
