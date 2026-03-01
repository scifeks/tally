"""RAG engine package for tally."""
from .engine import RAGEngine, get_ollama_models, verify_ollama_available

__all__ = ["RAGEngine", "get_ollama_models", "verify_ollama_available"]
