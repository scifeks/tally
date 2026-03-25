"""Best-effort ChromaDB metadata sync for analyst PATCH edits."""

from __future__ import annotations

import json
import logging
from typing import Any

from application.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

# Maps FindingPatchRequest field names → ChromaDB metadata key names.
_PATCH_TO_CHROMA: dict[str, str] = {
    "severity": "severity",
    "confidence": "confidence",
    "finding_type": "finding_type",
    "meta_remediation": "remediation",
    "meta_risk_type": "risk_type",
    "meta_owasp_name": "owasp_name",
    "meta_title": "title",
    "meta_tags": "tags",
}

# Request fields whose values must be serialised to JSON strings for ChromaDB.
_CHROMA_JSON_FIELDS: frozenset[str] = frozenset({"finding_type", "meta_tags"})

_SCA_TOOLS: frozenset[str] = frozenset(
    {"pip-audit", "npm-audit", "composer-audit", "osv-scanner"}
)


def _build_chroma_patch(
    finding: dict[str, Any], changed_fields: set[str]
) -> dict[str, Any]:
    """Build the metadata patch dict to apply to ChromaDB.

    Only includes fields present in ``changed_fields`` that have a
    corresponding ChromaDB metadata key.  Values for meta keys are
    read from the parsed ``finding["meta"]`` dict.
    """
    patch: dict[str, Any] = {}
    meta: dict[str, Any] = finding.get("meta") or {}

    for field in changed_fields:
        chroma_key = _PATCH_TO_CHROMA.get(field)
        if chroma_key is None:
            continue

        if field.startswith("meta_"):
            meta_key = field[len("meta_") :]
            value = meta.get(meta_key)
        else:
            value = finding.get(field)

        if value is None:
            continue

        if field in _CHROMA_JSON_FIELDS and isinstance(value, list):
            value = json.dumps(value)

        patch[chroma_key] = value

    return patch


def _where(*conditions: dict[str, Any]) -> dict[str, Any]:
    """Return a ChromaDB where clause for one or more condition dicts."""
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": list(conditions)}


def _collect_ids(result: dict[str, Any]) -> list[str]:
    """Extract document IDs from a ChromaDB .get() result."""
    ids = result.get("ids")
    return list(ids) if ids else []


def _locate_semgrep_gitleaks(
    finding: dict[str, Any],
    rag_engine: RAGEngine,
    tool: str,
    profile: str,
    meta: dict[str, Any],
) -> list[str]:
    chroma_fingerprint: str | None = meta.get("fingerprint")
    if chroma_fingerprint:
        result = rag_engine.get_documents(
            where=_where(
                {"tool": tool},
                {"profile": profile},
                {"fingerprint": chroma_fingerprint},
            ),
            include=[],
        )
    else:
        logger.warning(
            "Chroma sync: no scanner fingerprint in meta for tool=%s "
            "(finding id=%s) — falling back to tool+profile",
            tool,
            finding.get("id"),
        )
        result = rag_engine.get_documents(
            where=_where({"tool": tool}, {"profile": profile}),
            include=[],
        )
    return _collect_ids(result)


def _locate_nmap(
    finding: dict[str, Any],
    rag_engine: RAGEngine,
    profile: str,
) -> list[str]:
    host: str = finding.get("host") or ""
    port_raw = finding.get("port")
    finding_id = finding.get("id")

    if not host:
        logger.warning(
            "Chroma sync: nmap finding id=%s has no host — skipping", finding_id
        )
        return []

    ids: list[str] = []

    # Port-level chunk: discriminate by ip_address + port (integer in Chroma).
    if port_raw is not None:
        try:
            port_int = int(port_raw)
        except (ValueError, TypeError):
            port_int = None
        if port_int is not None:
            result = rag_engine.get_documents(
                where=_where(
                    {"tool": "nmap"},
                    {"profile": profile},
                    {"ip_address": host},
                    {"port": port_int},
                ),
                include=[],
            )
            ids.extend(_collect_ids(result))

    # Host-level chunk: query by ip_address, post-filter to docs without port.
    result = rag_engine.get_documents(
        where=_where({"tool": "nmap"}, {"profile": profile}, {"ip_address": host}),
        include=["metadatas"],
    )
    raw_ids: list[str] = result.get("ids") or []
    raw_metas: list[dict[str, Any]] = result.get("metadatas") or []
    for doc_id, doc_meta in zip(raw_ids, raw_metas):
        if doc_meta.get("port") is None and doc_id not in ids:
            ids.append(doc_id)

    return ids


def _locate_zap(
    finding: dict[str, Any],
    rag_engine: RAGEngine,
    profile: str,
) -> list[str]:
    url: str = finding.get("url") or ""
    if url:
        result = rag_engine.get_documents(
            where=_where({"tool": "zap"}, {"profile": profile}, {"url": url}),
            include=[],
        )
    else:
        result = rag_engine.get_documents(
            where=_where({"tool": "zap"}, {"profile": profile}),
            include=[],
        )
    return _collect_ids(result)


def _locate_sca(
    finding: dict[str, Any],
    rag_engine: RAGEngine,
    tool: str,
    profile: str,
) -> list[str]:
    vuln_id: str = finding.get("vulnerability_id") or ""
    pkg_name: str = finding.get("package_name") or ""
    conditions: list[dict[str, Any]] = [{"tool": tool}, {"profile": profile}]
    if vuln_id:
        conditions.append({"vulnerability_id": vuln_id})
    if pkg_name:
        conditions.append({"package_name": pkg_name})
    result = rag_engine.get_documents(where=_where(*conditions), include=[])
    return _collect_ids(result)


def _locate_fallback(
    finding: dict[str, Any],
    rag_engine: RAGEngine,
    tool: str,
    profile: str,
) -> list[str]:
    result = rag_engine.get_documents(
        where=_where({"tool": tool}, {"profile": profile}),
        include=[],
    )
    ids = _collect_ids(result)
    if len(ids) > 10:
        logger.warning(
            "Chroma sync: fallback lookup for unrecognised tool=%s returned "
            "%d docs (>10) — skipping to avoid unbounded sync",
            tool,
            len(ids),
        )
        return []
    return ids


def _get_doc_ids(finding: dict[str, Any], rag_engine: RAGEngine) -> list[str]:
    """Locate ChromaDB document IDs for a given SQLite finding row."""
    tool: str = finding.get("tool") or ""
    meta: dict[str, Any] = finding.get("meta") or {}
    profile: str = meta.get("profile") or ""
    finding_id = finding.get("id")

    if not tool or not profile:
        logger.warning(
            "Chroma sync: missing tool or profile for finding id=%s — skipping",
            finding_id,
        )
        return []

    try:
        if tool in ("semgrep", "gitleaks"):
            return _locate_semgrep_gitleaks(finding, rag_engine, tool, profile, meta)
        if tool == "nmap":
            return _locate_nmap(finding, rag_engine, profile)
        if tool == "zap":
            return _locate_zap(finding, rag_engine, profile)
        if tool in _SCA_TOOLS:
            return _locate_sca(finding, rag_engine, tool, profile)
        return _locate_fallback(finding, rag_engine, tool, profile)
    except Exception as exc:
        logger.warning(
            "Chroma sync: doc lookup failed for finding id=%s, tool=%s: %s",
            finding_id,
            tool,
            exc,
        )
        return []


async def sync_finding_to_chroma(
    finding: dict[str, Any],
    changed_fields: set[str],
    rag_engine: RAGEngine | None,
) -> None:
    """Best-effort ChromaDB metadata sync after a SQLite analyst PATCH.

    Locates Chroma document(s) for the given finding by tool-specific
    metadata queries, then applies a patch containing only the changed
    fields.  Never raises — all exceptions are caught and logged as
    warnings.  The PATCH endpoint returns 200 regardless of this
    function's outcome.
    """
    try:
        if rag_engine is None:
            logger.warning("Chroma sync: RAGEngine not available — skipping")
            return

        patch = _build_chroma_patch(finding, changed_fields)
        if not patch:
            return

        doc_ids = _get_doc_ids(finding, rag_engine)
        finding_id = finding.get("id")
        tool = finding.get("tool")

        if not doc_ids:
            logger.warning(
                "Chroma sync: no matching doc for finding id=%s, tool=%s — skipping",
                finding_id,
                tool,
            )
            return

        for doc_id in doc_ids:
            try:
                rag_engine.update_metadata(doc_id, patch)
            except Exception as exc:
                logger.warning(
                    "Chroma sync: update_metadata failed for doc_id=%s: %s",
                    doc_id,
                    exc,
                )
    except Exception as exc:
        logger.warning(
            "Chroma sync: unexpected error for finding id=%s: %s",
            finding.get("id"),
            exc,
        )
