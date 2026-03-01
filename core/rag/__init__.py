"""RAG engine package for tally."""
from .engine import RAGEngine, get_ollama_models, verify_ollama_available
from .ingestor import FindingIngestor

__all__ = ["RAGEngine", "get_ollama_models", "verify_ollama_available", "FindingIngestor"]
