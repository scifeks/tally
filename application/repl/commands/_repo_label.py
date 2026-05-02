"""Helpers for translating ``repo_id`` integers into displayable repo names.

The ``findings.repo`` (TEXT name) column was replaced with ``findings.repo_id``
(INT FK to ``repositories``). Renderers that show a repo column still want
the human-readable name, so they JOIN at render time via this module.

Usage::

    repos_by_id = build_repos_by_id(loaded_repositories)
    label = label_for(row.get("repo_id"), repos_by_id)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def build_repos_by_id(repos: Iterable[Any]) -> dict[int, str]:
    """Return ``{id: name}`` for repos that have a numeric DB id.

    Repository instances loaded by ``ConfigManager.load_repositories`` are
    expected to expose ``id`` (resolved against the ``repositories`` table)
    and ``name``; entries missing either are skipped silently.
    """
    out: dict[int, str] = {}
    for repo in repos:
        rid = getattr(repo, "id", None)
        name = getattr(repo, "name", None)
        if isinstance(rid, int) and isinstance(name, str) and name:
            out[rid] = name
    return out


def label_for(repo_id: Any, repos_by_id: dict[int, str]) -> str:
    """Map ``repo_id`` to its repo name.

    Returns ``""`` when ``repo_id`` is None or missing from the lookup;
    matches the legacy renderer behavior when ``findings.repo`` was NULL.
    Soft-deleted repos may still appear in ``repos_by_id`` if the caller
    chose not to filter; this module does not enforce a policy.
    """
    if repo_id is None:
        return ""
    if not isinstance(repo_id, int):
        try:
            repo_id = int(repo_id)
        except (TypeError, ValueError):
            return ""
    return repos_by_id.get(repo_id, "")
