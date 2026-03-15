"""RAG engine package for tally."""

from core.llm.ollama_adapter import get_ollama_models, verify_ollama_available
from core.repl.search_command_parser import SearchValidationError

from .engine import RAGEngine
from .enrichment import EnrichmentPipeline
from .ingestor import FindingIngestor
from .query import QueryEngine

__all__ = [
    "RAGEngine",
    "get_ollama_models",
    "verify_ollama_available",
    "EnrichmentPipeline",
    "FindingIngestor",
    "QueryEngine",
    "SearchValidationError",
]
