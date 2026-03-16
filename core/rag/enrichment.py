"""LLM-based enrichment pipeline for ChromaDB security findings."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any

from rich.console import Console

from core.llm import LLMProvider, get_llm_provider
from core.tools.constants import (
    CONFIDENCE_LEVELS,
    ENRICHMENT_FIELDS,
    SEVERITY_LEVELS,
)

from .engine import RAGEngine
from .ingestor import ChunkBuilderFactory

if TYPE_CHECKING:
    from core.store.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a security finding classifier. "
    "You output only valid JSON. "
    "No prose, no explanation, no markdown. Only a JSON object."
)

_USER_PROMPT_TEMPLATE = (
    "Classify this security finding. Return only a JSON object with the fields"
    " listed below. Do not include fields that are not listed."
    " Do not add explanation or prose.\n"
    "\n"
    "Finding:\n"
    "{document_text}\n"
    "\n"
    "Fields to populate: {fields_to_enrich}\n"
    "\n"
    "Field definitions:\n"
    "- risk_type: The specific vulnerability or condition using OWASP Top 10 2021"
    " or CWE naming in snake_case. Priority order:\n"
    "  1. If a CWE ID is present in the finding, derive from CWE name"
    " (e.g. CWE-79 -> cross_site_scripting)\n"
    "  2. If no CWE, use OWASP Top 10 2021 category in snake_case\n"
    "  3. If neither applies, use a concise snake_case label a security"
    " professional would recognize\n"
    "- remediation: One to two sentences maximum."
    " Specific and actionable. No padding, no generic advice.\n"
    "- severity: How bad is the impact if exploited. Must be exactly one of:"
    " critical, high, medium, low, informational\n"
    "  - critical: system compromise, data breach, full authentication bypass\n"
    "  - high: significant data exposure, privilege escalation, remote code execution\n"
    "  - medium: limited data exposure, requires user interaction\n"
    "  - low: minimal impact, difficult to exploit\n"
    "  - informational: fact about attack surface, no direct exploitability\n"
    "- confidence: How certain are we this is exploitable. Must be exactly one of:"
    " confirmed, probable, potential\n"
    "  - confirmed: exploitable as found, no conditions required\n"
    "  - probable: very likely exploitable with minimal conditions\n"
    "  - potential: condition exists but requires specific circumstances\n"
    "- description: One sentence describing what was found. No padding.\n"
    "\n"
    "Only include fields from this list: {fields_to_enrich}"
)

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class EnrichmentPipeline:
    """Enriches ChromaDB findings with LLM-generated semantic fields.

    LLM calls run concurrently via ThreadPoolExecutor (Phase 2).
    ChromaDB writes are serialized after all LLM calls complete (Phase 3).
    Skips findings already marked ``enriched: True``.
    """

    def __init__(
        self,
        rag_engine: RAGEngine,
        console: Console | None = None,
        sqlite_store: SQLiteStore | None = None,
        run_id: int | None = None,
        llm_provider: LLMProvider | None = None,
        max_workers: int = 4,
    ) -> None:
        self._engine = rag_engine
        self._console = console
        self._sqlite_store = sqlite_store
        self._run_id = run_id
        self._llm_provider = llm_provider  # resolved lazily on first _call_llm
        self._max_workers = max_workers

    @property
    def _provider(self) -> LLMProvider:
        """Return the LLM provider, resolving from config on first access."""
        if self._llm_provider is None:
            self._llm_provider = get_llm_provider("enrichment", self._engine.base_path)
        return self._llm_provider

    def _resolve_max_workers(self) -> int:
        """Read enrichment_max_concurrency from global config; fall back to default."""
        try:
            from core.config.manager import ConfigManager

            cfg = ConfigManager(str(self._engine.base_path)).global_config
            return cfg.enrichment_max_concurrency
        except Exception:
            return self._max_workers

    def enrich(self, ids: list[str]) -> None:
        """Enrich a list of document IDs in place.

        Phase 1 (sequential): Fetch docs from ChromaDB, build work list.
        Phase 2 (concurrent): Run LLM calls in a thread pool.
        Phase 3 (sequential): Write validated metadata back to ChromaDB.
        Failures on individual findings are logged but do not stop the pipeline.
        """
        if not ids:
            return

        total = len(ids)
        max_workers = self._resolve_max_workers()

        # Phase 1: Fetch and classify (sequential — ChromaDB reads)
        work_items: list[tuple[str, str, dict[str, Any], list[str]]] = []
        auto_enriched = 0
        for doc_id in ids:
            doc = self._engine.get_document_by_id(doc_id)
            if doc is None:
                logger.warning("Document %s not found; skipping enrichment", doc_id)
                continue
            if doc["metadata"].get("enriched"):
                auto_enriched += 1
                continue
            fields = self._get_fields_to_enrich(doc["metadata"])
            if not fields:
                self._engine.update_metadata(doc_id, {"enriched": True})
                auto_enriched += 1
                continue
            work_items.append((doc_id, doc["document"], doc["metadata"], fields))

        # Phase 2: LLM calls (concurrent)
        updates: list[tuple[str, dict[str, Any]]] = []
        completed = 0
        n_work = len(work_items)

        if work_items:
            # Pre-resolve LLM provider once before spawning threads
            _ = self._provider

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {
                executor.submit(self._call_llm_worker, text, meta, fields): doc_id
                for doc_id, text, meta, fields in work_items
            }
            for future in as_completed(future_to_id):
                doc_id = future_to_id[future]
                completed += 1
                if self._console:
                    self._console.print(
                        f"[dim]Enriching findings... {completed}/{n_work}[/dim]",
                        end="\r",
                    )
                try:
                    validated = future.result()
                    validated["enriched"] = True
                    updates.append((doc_id, validated))
                except Exception as exc:
                    logger.error("Enrichment failed for %s: %s", doc_id, exc)

        # Phase 3: ChromaDB writes (sequential — avoids write contention)
        for doc_id, validated in updates:
            self._engine.update_metadata(doc_id, validated)

        enriched_count = len(updates) + auto_enriched
        if self._console:
            self._console.print()  # newline after \r progress
            msg = (
                f"[dim]Enrichment complete."
                f" {enriched_count}/{total} findings enriched.[/dim]"
            )
            self._console.print(msg)

        self._sqlite_upsert(ids)

    def _sqlite_upsert(self, ids: list[str]) -> None:
        """Write enriched findings to SQLite after enrich() completes.

        Failures are logged and never propagate to the caller.
        """
        if self._sqlite_store is None or self._run_id is None:
            return
        try:
            findings: list[dict[str, Any]] = []
            for doc_id in ids:
                doc = self._engine.get_document_by_id(doc_id)
                if doc is not None:
                    findings.append(doc["metadata"])
            if findings:
                self._sqlite_store.upsert_findings(self._run_id, findings)
        except Exception as exc:
            logger.error("SQLite upsert failed after enrichment: %s", exc)

    def _call_llm_worker(
        self, doc_text: str, metadata: dict[str, Any], fields: list[str]
    ) -> dict[str, Any]:
        """Thread-safe worker: call LLM and validate. Raises on failure."""
        raw = self._call_llm(doc_text, metadata, fields)
        return self._validate_response(raw, fields)

    def _get_fields_to_enrich(self, metadata: dict[str, Any]) -> list[str]:
        """Return list of ENRICHMENT_FIELDS keys that still need values."""
        tool = metadata.get("tool", "")
        _builder = ChunkBuilderFactory.load(tool)
        tool_provided = (
            _builder.non_enriched_fields if _builder is not None else frozenset()
        )
        fields = []
        for field in ENRICHMENT_FIELDS:
            if field in tool_provided:
                continue
            if metadata.get(field):
                continue
            fields.append(field)
        return fields

    def _call_llm(
        self, doc_text: str, metadata: dict[str, Any], fields: list[str]
    ) -> dict[str, Any]:
        """Call LLM provider and return the parsed JSON dict. Raises on failure."""
        prompt = _USER_PROMPT_TEMPLATE.format(
            document_text=doc_text,
            fields_to_enrich=", ".join(fields),
        )
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        content = self._provider.chat(messages, temperature=0.1, num_predict=500)
        return json.loads(content or "")

    def _validate_response(
        self, raw: dict[str, Any], requested_fields: list[str]
    ) -> dict[str, Any]:
        """Validate LLM response dict. Returns only safe, valid fields."""
        valid: dict[str, Any] = {}
        allowed = set(requested_fields)

        for key, val in raw.items():
            if key not in allowed:
                continue  # ignore unexpected fields
            if not isinstance(val, str) or not val.strip():
                logger.warning(
                    "Enrichment: field %r has empty/non-string value; omitting", key
                )
                continue
            if key == "severity" and val not in SEVERITY_LEVELS:
                logger.warning("Enrichment: invalid severity %r; omitting", val)
                continue
            if key == "confidence" and val not in CONFIDENCE_LEVELS:
                logger.warning("Enrichment: invalid confidence %r; omitting", val)
                continue
            if key == "risk_type" and not _SNAKE_CASE_RE.match(val):
                logger.warning("Enrichment: risk_type %r not snake_case; omitting", val)
                continue
            valid[key] = val

        return valid
