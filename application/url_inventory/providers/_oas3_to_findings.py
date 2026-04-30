"""Shared OAS3 → UrlFinding conversion helpers used by every provider.

UserFileProvider, KatanaProvider, and NoirProvider all reduce their input
to an OAS3 document and walk ``paths × methods``. The differences are
in the row's ``source``, ``tool``, ``run_id``, and ``file_path`` — those
are passed in by the caller; the iteration shape is shared.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool
from domain.url_inventory.vendor_filter import is_vendor_path

if TYPE_CHECKING:
    from application.url_inventory.ports import UrlProviderContext


_ALLOWED_METHODS: frozenset[str] = frozenset(
    {"get", "post", "put", "delete", "patch", "head", "options"}
)


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
    never enter ``url_findings``. ``Repository.ignore_dirs`` is folded
    in alongside the static indicators so user-configured exclusions
    also apply to URL discovery.
    """
    base_protocol, base_host, base_port = resolve_base(doc, ctx)
    extra_indicators = tuple(getattr(ctx.repo, "ignore_dirs", ()) or ())
    paths = doc.get("paths") or {}
    if not isinstance(paths, dict):
        return
    for raw_path, ops in paths.items():
        if not isinstance(ops, dict):
            continue
        path_str = raw_path if isinstance(raw_path, str) else str(raw_path)
        if is_vendor_path(path_str, extra_indicators=extra_indicators):
            continue
        for method_key, op in ops.items():
            method = method_key.lower() if isinstance(method_key, str) else ""
            if method not in _ALLOWED_METHODS:
                continue
            meta: dict[str, Any] = {}
            if isinstance(op, dict):
                meta["original_file"] = op
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
    2. First entry of ``ctx.repo.base_urls``.
    3. Hard fallback: ``https://localhost:443``.
    """
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict):
            url = first.get("url")
            if isinstance(url, str) and "://" in url:
                return parse_url(url)
    base_urls = list(ctx.repo.base_urls or [])
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
