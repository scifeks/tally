"""RAG engine package for tally."""

from .engine import RAGEngine, get_ollama_models, verify_ollama_available
from .enrichment import EnrichmentPipeline
from .ingestor import FindingIngestor
from .query import QueryEngine
from .search_parser import SearchValidationError

__all__ = [
    "RAGEngine",
    "get_ollama_models",
    "verify_ollama_available",
    "EnrichmentPipeline",
    "FindingIngestor",
    "QueryEngine",
    "SearchValidationError",
]
