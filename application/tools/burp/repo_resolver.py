"""Resolve a URL to the project repository that serves it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from core.config.schemas.repository import Repository


def resolve_repo_by_url(
    url: str,
    repos: Sequence[Repository],
) -> tuple[str, int | None]:
    """Match a URL against repos' service base_urls.

    Returns (repo_name, repo_id) for the longest matching
    base_url prefix, or ("", None) when no repo matches.
    """
    if not url:
        return "", None

    normalized = _normalize(url)
    best_name = ""
    best_id: int | None = None
    best_len = 0

    for repo in repos:
        for svc in repo.services:
            for base in svc.base_urls:
                base_norm = _normalize(base)
                if not base_norm:
                    continue
                if normalized.startswith(base_norm):
                    if len(base_norm) > best_len:
                        best_len = len(base_norm)
                        best_name = repo.name
                        best_id = repo.id
    return best_name, best_id


def _normalize(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    return f"{base}{path}"
