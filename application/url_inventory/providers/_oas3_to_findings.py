"""Convert OAS3 documents to UrlFinding rows for all providers.

Each provider reduces its input to an OAS3 document and walks paths and
methods. Differences in source, tool, run_id, and file_path are passed in
by the caller; the iteration shape is shared.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from core.config.schemas.repository import build_excluded_dirs
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool
from domain.url_inventory.vendor_filter import is_vendor_path

if TYPE_CHECKING:
    from application.url_inventory.ports import UrlProviderContext


_ALLOWED_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options"}
)


def _dedup_parameters(op: dict) -> dict:
    params = op.get("parameters")
    if not isinstance(params, list) or len(params) <= 1:
        return op
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for p in params:
        if not isinstance(p, dict):
            deduped.append(p)
            continue
        key = (p.get("name", ""), p.get("in", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    if len(deduped) == len(params):
        return op
    result = dict(op)
    result["parameters"] = deduped
    return result


def iter_oas3_rows(
    doc: dict,
    ctx: UrlProviderContext,
    *,
    source: UrlSource,
    tool: UrlTool | None,
    run_id: int | None,
    file_path: str | None,
) -> Iterator[UrlFinding]:
    """Yield ``UrlFinding`` rows from an OAS3 *doc* + repo *ctx*.

    The caller specifies ``source`` / ``tool`` / ``run_id`` / ``file_path``
    so the same iterator serves user uploads (USER/None/None/<path>),
    Katana scans (SCAN/KATANA/<run>/None), and Noir scans
    (SCAN/NOIR/<run>/None).

    Paths that look like vendor / dependency directories are dropped at
    this gate (single ingest boundary for every URL provider) so they
    never enter ``url_findings``. Service exclusions (test_dirs and
    ignore_dirs) are folded in alongside the static indicators so
    user-configured exclusions also apply to URL discovery.
    """
    base_protocol, base_host, base_port = resolve_base(doc, ctx)
    extra_indicators = (
        tuple(build_excluded_dirs(ctx.repo.services[0])) if ctx.repo.services else ()
    )
    paths = doc.get("paths") or {}
    if not isinstance(paths, dict):
        return
    for raw_path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        path_str = raw_path if isinstance(raw_path, str) else str(raw_path)
        if path_str and not path_str.startswith("/"):
            path_str = "/" + path_str
        if is_vendor_path(path_str, extra_indicators=extra_indicators):
            continue
        for method_key, op in ops.items():
            method = method_key.lower() if isinstance(method_key, str) else ""
            if method not in _ALLOWED_METHODS:
                continue
            meta: dict[str, Any] = {}
            if isinstance(op, dict):
                meta["original_file"] = _dedup_parameters(op)
            yield UrlFinding(
                repo_id=ctx.repo_id,
                source=source,
                tool=tool,
                run_id=run_id,
                method=method.upper(),
                protocol=base_protocol,
                host=base_host,
                port=base_port,
                path=path_str,
                file_path=file_path,
                meta=meta,
            )


def resolve_base(
    doc: dict,
    ctx: UrlProviderContext,
) -> tuple[str, str, int]:
    """Resolve (protocol, host, port) from the doc's servers or repo base_urls.

    Order of precedence:
    1. First entry of ``doc['servers']`` (if it has a parseable URL).
    2. First entry of service base_urls from ctx.repo.services[0].
    3. Hard fallback: ``https://localhost:443``.
    """
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict):
            url = first.get("url")
            if isinstance(url, str) and "://" in url:
                return parse_url(url)
    base_urls = []
    if ctx.repo.services and ctx.repo.services[0].base_urls:
        base_urls = list(ctx.repo.services[0].base_urls)
    if base_urls:
        return parse_url(base_urls[0])
    return ("https", "localhost", 443)


def parse_url(url: str) -> tuple[str, str, int]:
    """Return (protocol, host, port) from *url*; default ports per scheme."""
    parsed = urlparse(url)
    protocol = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "localhost").lower()
    if parsed.port is not None:
        port = parsed.port
    elif protocol == "http":
        port = 80
    else:
        port = 443
    return (protocol, host, port)
