"""Embedding provider adapters."""

from .base import EmbeddingAdapterError, EmbeddingProvider
from .factory import get_embedding_provider
from .ollama_embedding_adapter import OllamaEmbeddingAdapter

__all__ = [
    "EmbeddingProvider",
    "EmbeddingAdapterError",
    "OllamaEmbeddingAdapter",
    "get_embedding_provider",
]
