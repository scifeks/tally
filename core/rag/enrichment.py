"""LLM-based enrichment pipeline for ChromaDB security findings."""

import json
import logging
import re
from typing import Any

import ollama
from rich.console import Console

from core.tools.constants import (
    ENRICHMENT_FIELDS,
    SEVERITY_LEVELS,
    TOOL_PROVIDED_FIELDS,
)

from .engine import RAGEngine

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
    "- severity: Must be exactly one of:"
    " confirmed, probable, potential, informational\n"
    "  - confirmed: exploitable as found\n"
    "  - probable: very likely exploitable with minimal conditions\n"
    "  - potential: condition exists but requires specific circumstances\n"
    "  - informational: fact about attack surface, no direct exploitability\n"
    "- description: One sentence describing what was found. No padding.\n"
    "\n"
    "Only include fields from this list: {fields_to_enrich}"
)

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class EnrichmentPipeline:
    """Enriches ChromaDB findings with LLM-generated semantic fields.

    Processes one finding at a time, sequentially and synchronously.
    Skips findings already marked ``enriched: True``.
    """

    def __init__(self, rag_engine: RAGEngine, console: Console | None = None) -> None:
        self._engine = rag_engine
        self._console = console

    def enrich(self, ids: list[str]) -> None:
        """Enrich a list of document IDs in place.

        Fetches each document, determines which fields need enrichment,
        calls the LLM, validates the response, and updates metadata.
        Failures on individual findings are logged but do not stop the pipeline.
        """
        if not ids:
            return

        total = len(ids)
        enriched_count = 0

        for i, doc_id in enumerate(ids, 1):
            if self._console:
                self._console.print(
                    f"[dim]Enriching findings... {i}/{total}[/dim]", end="\r"
                )
            try:
                enriched_count += self._enrich_one(doc_id)
            except Exception as exc:
                logger.error("Enrichment failed for %s: %s", doc_id, exc)

        if self._console:
            self._console.print()  # newline after \r progress
            msg = (
                f"[dim]Enrichment complete."
                f" {enriched_count}/{total} findings enriched.[/dim]"
            )
            self._console.print(msg)

    def _enrich_one(self, doc_id: str) -> int:
        """Enrich a single document. Returns 1 if processed, 0 if skipped/failed."""
        doc = self._engine.get_document_by_id(doc_id)
        if doc is None:
            logger.warning("Document %s not found; skipping enrichment", doc_id)
            return 0

        if doc["metadata"].get("enriched"):
            return 1  # already done

        fields = self._get_fields_to_enrich(doc["metadata"])
        if not fields:
            self._engine.update_metadata(doc_id, {"enriched": True})
            return 1

        raw = self._call_llm(doc["document"], doc["metadata"], fields)
        validated = self._validate_response(raw, fields)
        validated["enriched"] = True
        self._engine.update_metadata(doc_id, validated)
        return 1

    def _get_fields_to_enrich(self, metadata: dict[str, Any]) -> list[str]:
        """Return list of ENRICHMENT_FIELDS keys that still need values."""
        tool = metadata.get("tool", "")
        tool_provided = TOOL_PROVIDED_FIELDS.get(tool, set())
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
        """Call Ollama and return the parsed JSON dict. Raises on failure."""
        prompt = _USER_PROMPT_TEMPLATE.format(
            document_text=doc_text,
            fields_to_enrich=", ".join(fields),
        )
        client = ollama.Client(host=self._engine.ollama_base_url)
        response = client.chat(
            model=self._engine.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.1, "num_predict": 500},
        )
        msg = response.message if hasattr(response, "message") else response["message"]
        content = msg.content if hasattr(msg, "content") else msg["content"]
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
            if key == "risk_type" and not _SNAKE_CASE_RE.match(val):
                logger.warning("Enrichment: risk_type %r not snake_case; omitting", val)
                continue
            valid[key] = val

        return valid
