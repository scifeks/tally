"""Stable document identifiers for finding entries in the vector index."""


def finding_vector_id(fingerprint: str, profile: str) -> str:
    """Build a stable vector-index document id for a finding.

    Joining fingerprint and profile with a colon yields an id that keeps
    re-scans of the same finding on the same profile at the same
    document. Findings that disappear between scans remain in the index
    under their prior id.
    """
    return f"{fingerprint}:{profile}"
