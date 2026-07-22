"""ChromaDB document ID construction from finding fingerprints."""


def chromadb_doc_id(fingerprint: str, profile: str) -> str:
    """Construct a stable ChromaDB doc ID from fingerprint and profile.

    Returns a colon-separated ID that allows re-scanning the same finding
    to upsert (update) the existing ChromaDB document instead of creating
    duplicates. Findings that disappear between scans persist in ChromaDB.
    """
    return f"{fingerprint}:{profile}"
