"""Parse LLM JSON responses and convert to UrlFinding domain objects."""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from application.url_inventory.file_scanner import find_route_files
from application.url_inventory.prompts.endpoint_extraction import (
    build_extraction_prompt,
)
from application.url_inventory.service import UrlInventoryService
from domain.url_inventory.entry import UrlFinding, UrlSource, UrlTool

if TYPE_CHECKING:
    from application.ports.llm_provider import LLMProvider
    from application.ports.url_finding_repository import UrlFindingRepositoryPort

_VALID_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
_logger = logging.getLogger(__name__)


def parse_extraction_response(text: str) -> list[dict[str, Any]]:
    """Parse LLM JSON response into endpoint dicts.

    Handles code fences (```json...```), embedded JSON in prose, and
    normalizes methods to uppercase. Filters invalid HTTP methods.
    Returns empty list on parse failure.
    """
    json_text = _extract_json(text)
    if not json_text:
        return []

    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return []

    endpoints = data.get("endpoints")
    if not isinstance(endpoints, list):
        return []

    result = []
    for ep in endpoints:
        if not isinstance(ep, dict):
            continue

        raw_method = ep.get("method", "")
        if not isinstance(raw_method, str):
            continue
        method = raw_method.upper()
        if method not in _VALID_METHODS:
            continue

        normalized = dict(ep)
        normalized["method"] = method
        normalized.setdefault("query_params", [])
        normalized.setdefault("form_params", [])
        result.append(normalized)

    return result


def to_url_findings(
    endpoints: list[dict[str, Any]],
    *,
    repo_id: int,
    run_id: int | None,
    host: str,
    port: int,
    protocol: str,
) -> list[UrlFinding]:
    """Convert endpoint dicts to UrlFinding entries."""
    findings = []
    for ep in endpoints:
        path = ep.get("path", "")
        method = ep.get("method", "")
        query_params = ep.get("query_params", [])
        form_params = ep.get("form_params", [])

        path_params = _extract_path_params(path)

        parameters = []
        parameters.extend({"name": name, "in": "query"} for name in query_params)
        parameters.extend({"name": name, "in": "formData"} for name in form_params)
        parameters.extend({"name": name, "in": "path"} for name in path_params)

        meta = {"original_file": {"parameters": parameters}}

        finding = UrlFinding(
            repo_id=repo_id,
            source=UrlSource.SCAN,
            tool=UrlTool.LLM,
            run_id=run_id,
            method=method,
            protocol=protocol,
            host=host,
            port=port,
            path=path,
            meta=meta,
        )
        findings.append(finding)

    return findings


def _extract_json(text: str) -> str:
    """Extract JSON from code fence or embedded in prose."""
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if match:
        return match.group(1)

    start_idx = text.find("{")
    if start_idx == -1:
        return ""

    end_idx = text.rfind("}")
    if end_idx == -1 or end_idx <= start_idx:
        return ""

    return text[start_idx : end_idx + 1]


def _extract_path_params(path: str) -> list[str]:
    """Extract parameter names from {name} patterns in path."""
    seen = set()
    result = []
    for match in re.finditer(r"\{([^}]+)\}", path):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


class LlmEndpointExtractor:
    """Orchestrates LLM-based HTTP endpoint extraction from source code."""

    def __init__(
        self,
        llm_provider: LLMProvider,
        url_finding_repo: UrlFindingRepositoryPort,
        max_chars_per_batch: int = 30_000,
        max_files: int = 50,
    ) -> None:
        self._provider = llm_provider
        self._url_repo = url_finding_repo
        self._max_chars_per_batch = max_chars_per_batch
        self._max_files = max_files

    def extract_for_repo(
        self,
        *,
        repo_path: str,
        repo_id: int,
        run_id: int | None,
        host: str,
        port: int,
        protocol: str,
        excluded_dirs: list[str] | None = None,
    ) -> int:
        """Extract endpoints and store as UrlFinding rows. Returns count."""
        files = find_route_files(repo_path, excluded_dirs, max_files=self._max_files)
        if not files:
            _logger.info("No route files found in %s for LLM extraction", repo_path)
            return 0

        file_tuples: list[tuple[str, str]] = []
        for file_path in files:
            try:
                content = file_path.read_text(errors="replace")
                rel_path = str(file_path.relative_to(repo_path))
                file_tuples.append((rel_path, content))
            except Exception as e:
                _logger.warning("Failed to read file %s: %s", file_path, e)

        if not file_tuples:
            return 0

        batches = self._batch_files(file_tuples)
        all_endpoints: list[dict[str, Any]] = []
        seen_endpoints: set[tuple[str, str]] = set()
        total_prompt_chars = 0

        for batch in batches:
            try:
                prompt = build_extraction_prompt(batch)
                total_prompt_chars += len(prompt)
                response = self._provider.complete(prompt, temperature=0.1)
                parsed = parse_extraction_response(response)

                for endpoint in parsed:
                    key = (
                        endpoint.get("method", ""),
                        endpoint.get("path", ""),
                    )
                    if key not in seen_endpoints:
                        seen_endpoints.add(key)
                        all_endpoints.append(endpoint)
            except Exception as e:
                _logger.error("LLM extraction failed for batch: %s", e)
                return 0

        if not all_endpoints:
            _logger.info("No endpoints extracted from %s", repo_path)
            service = UrlInventoryService(self._url_repo)
            service.ingest_scan_source(
                repo_id=repo_id,
                run_id=run_id,
                tool=UrlTool.LLM,
                entries=[],
            )
            return 0

        findings = to_url_findings(
            all_endpoints,
            repo_id=repo_id,
            run_id=run_id,
            host=host,
            port=port,
            protocol=protocol,
        )

        service = UrlInventoryService(self._url_repo)
        count = service.ingest_scan_source(
            repo_id=repo_id,
            run_id=run_id,
            tool=UrlTool.LLM,
            entries=findings,
        )

        _logger.info(
            "Extracted %d endpoints from %d files (%d batches, %d prompt chars)",
            len(all_endpoints),
            len(file_tuples),
            len(batches),
            total_prompt_chars,
        )
        return count

    def _batch_files(self, files: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
        """Split files into batches by total character count."""
        batches: list[list[tuple[str, str]]] = []
        current_batch: list[tuple[str, str]] = []
        current_size = 0

        for path, content in files:
            file_size = len(content)
            if file_size > self._max_chars_per_batch:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_size = 0
                batches.append([(path, content)])
            elif current_size + file_size > self._max_chars_per_batch:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [(path, content)]
                current_size = file_size
            else:
                current_batch.append((path, content))
                current_size += file_size

        if current_batch:
            batches.append(current_batch)

        return batches
