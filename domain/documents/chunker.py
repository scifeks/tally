"""Character-count text chunker with overlap."""

from __future__ import annotations


def chunk_text(
    text: str,
    chunk_size: int = 2000,
    overlap: int = 400,
) -> list[str]:
    """Split text into overlapping chunks by character count."""
    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks
