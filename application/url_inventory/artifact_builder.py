"""Rebuild merged seeds.txt and merged_oas3.json from the URL inventory DB.

The ``url_findings`` table is the source of truth; on-disk artifacts are
derived just-in-time before each scan tool that needs them. Each row's
``meta.original_file`` carries the source-format fragment (an OAS3 operation
object, a HAR entry, a Postman request) so the merged document can be
rebuilt faithfully without re-reading the user-uploaded source files.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.config._atomic import atomic_write_text
from core.project_paths import ProjectPaths
from domain.url_inventory.entry import UrlFinding
from domain.url_inventory.normalise import normalise_url


def _query_string_from_meta(meta: dict[str, Any]) -> str:
    """Extract query param names from OAS3 operation metadata."""
    original = meta.get("original_file")
    if not isinstance(original, dict):
        return ""
    params = original.get("parameters")
    if not isinstance(params, list):
        return ""
    names = list(
        dict.fromkeys(
            p["name"]
            for p in params
            if isinstance(p, dict)
            and p.get("in") == "query"
            and isinstance(p.get("name"), str)
        )
    )
    if not names:
        return ""
    return "?" + "&".join(f"{n}=" for n in names)


def _seed_url(row: UrlFinding) -> str:
    """Return the seed-file URL for *row* (one URL per line for tools)."""
    if (row.protocol == "http" and row.port == 80) or (
        row.protocol == "https" and row.port == 443
    ):
        base = f"{row.protocol}://{row.host}{row.path}"
    else:
        base = f"{row.protocol}://{row.host}:{row.port}{row.path}"
    return base + _query_string_from_meta(row.meta)


def build_seeds(rows: Iterable[UrlFinding]) -> str:
    """Render *rows* as a newline-delimited seeds file.

    Dedup canonicalizes host case, strips default ports and trailing
    slashes so multi-source rows that resolve to the same URL collapse
    to one seed line.
    """
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        url = _seed_url(row)
        key = normalise_url(url)
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    return "\n".join(out) + ("\n" if out else "")


def build_oas3(rows: Iterable[UrlFinding], *, base_url: str | None = None) -> dict:
    """Build merged OAS3 document from *rows*."""
    paths: dict[str, dict[str, Any]] = {}
    server_url: str | None = base_url

    for row in rows:
        method = row.method.lower()
        path_key = row.path or "/"
        original = row.meta.get("original_file")
        if isinstance(original, dict) and (
            "responses" in original or "parameters" in original
        ):
            operation = dict(original)
        else:
            operation = {
                "summary": f"{row.method} {row.path}",
                "responses": {"200": {"description": ""}},
            }
        paths.setdefault(path_key, {})[method] = operation

        if server_url is None:
            scheme = row.protocol
            if (scheme == "http" and row.port == 80) or (
                scheme == "https" and row.port == 443
            ):
                server_url = f"{scheme}://{row.host}"
            else:
                server_url = f"{scheme}://{row.host}:{row.port}"

    doc: dict[str, Any] = {
        "openapi": "3.0.0",
        "info": {"title": "Tally URL inventory", "version": "1.0.0"},
        "paths": paths,
    }
    if server_url is not None:
        doc["servers"] = [{"url": server_url}]
    return doc


def write_artifacts(
    project_paths: ProjectPaths,
    repo_dir_key: str,
    rows: list[UrlFinding],
    *,
    base_url: str | None = None,
) -> tuple[str, str]:
    """Write merged_urls.txt and merged_oas3.json under
    ``endpoints/<repo_dir_key>/``. Atomic writes; returns the absolute
    paths of the two files (for callers to pass to ZAP/XSStrike/DalFox).
    """
    import json

    out_dir = project_paths.endpoint_dir(repo_dir_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    seeds_path = out_dir / "merged_urls.txt"
    oas3_path = out_dir / "merged_oas3.json"
    atomic_write_text(seeds_path, build_seeds(rows))
    atomic_write_text(
        oas3_path, json.dumps(build_oas3(rows, base_url=base_url), indent=2)
    )
    return str(seeds_path), str(oas3_path)
