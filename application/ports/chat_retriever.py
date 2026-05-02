"""Port for the chat-side retrieval seam.

Lets the chat service consume any retriever shape without coupling to
``application.rag.query.QueryEngine``. Production passes the
``QueryEngine`` directly; tests inject a stub that returns canned
matches without standing up a real knowledge base.
"""

from __future__ import annotations

from typing import Any, Protocol

from application.ports.vector_index import VectorMatch


class ChatRetriever(Protocol):
    def search(
        self,
        raw_input: str = "",
        n_results: int = 20,
        query: Any = None,
    ) -> list[VectorMatch]: ...
