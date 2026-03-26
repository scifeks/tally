"""RAG engine package for tally."""

from core.exceptions import SearchValidationError
from core.llm.ollama_adapter import get_ollama_models, verify_ollama_available

from .engine import RAGEngine
from .enrichment import EnrichmentPipeline
from .query import QueryEngine

__all__ = [
    "RAGEngine",
    "get_ollama_models",
    "verify_ollama_available",
    "EnrichmentPipeline",
    "QueryEngine",
    "SearchValidationError",
]
