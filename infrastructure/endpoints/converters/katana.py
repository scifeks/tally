"""Katana adapter — converts Katana JSONL crawl output to OAS3.

Actual Katana JSONL schema (verified from katana -j output):
    {
        "timestamp": "...",
        "request": {
            "method": "GET",
            "endpoint": "https://example.com/path?q=1",
            "raw": "GET /path?q=1 HTTP/1.1\\r\\n..."
        },
        "response": {
            "status_code": 200,
            "headers": {"content-type": "text/html", ...},
            "body": "...",
            "content_length": 528,
            "raw": "HTTP/1.1 200 OK\\r\\n..."
        }
    }

Note:
- request.endpoint contains the full URL (scheme + host + path + query).
- response.headers keys are lowercase.
- There is no request.body field; body is embedded in request.raw only.
  POST requestBody is populated from response Content-Type when present.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .base import ConverterAdapter, ConverterError


class KatanaAdapter(ConverterAdapter):
    """Adapter for Katana JSONL files — converts to OAS3."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".jsonl"})

    def validate(self, path: Path) -> None:
        """Check that file is a valid Katana JSONL document."""
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConverterError(f"Cannot read file: {exc}") from exc

        lines = [ln for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise ConverterError("File contains no JSONL records")

        found_endpoint = False
        for i, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ConverterError(f"Line {i} is not valid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ConverterError(f"Line {i} is not a JSON object")
            req = record.get("request", {})
            if isinstance(req, dict) and req.get("endpoint"):
                found_endpoint = True

        if not found_endpoint:
            raise ConverterError("No record contains a 'request.endpoint' field")

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert Katana JSONL entries to an OAS3 JSON document."""
        text = source.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]

        paths: dict[str, dict] = {}
        seen: set[tuple[str, str]] = set()

        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            request = record.get("request", {})
            response = record.get("response", {})
            if not isinstance(request, dict):
                continue

            url = request.get("endpoint", "")
            if not url:
                continue

            method = request.get("method", "GET").lower()
            parsed = urlparse(url)
            url_path = parsed.path or "/"
            key = (url_path, method)
            if key in seen:
                continue
            seen.add(key)

            query_params = [
                {
                    "in": "query",
                    "name": name,
                    "schema": {"type": "string"},
                }
                for name in parse_qs(parsed.query, keep_blank_values=True)
            ]

            status_code = 200
            if isinstance(response, dict):
                raw_status = response.get("status_code", 200)
                if isinstance(raw_status, int):
                    status_code = raw_status

            content_type: str | None = None
            if isinstance(response, dict):
                headers = response.get("headers", {})
                if isinstance(headers, dict):
                    content_type = headers.get("content-type")

            response_obj: dict = {"description": "Response"}
            if content_type:
                response_obj["content"] = {content_type: {"schema": {"type": "object"}}}

            operation: dict = {
                "parameters": query_params,
                "responses": {str(status_code): response_obj},
            }

            if method in {"post", "put", "patch"} and content_type:
                operation["requestBody"] = {
                    "content": {content_type: {"schema": {"type": "object"}}}
                }

            if url_path not in paths:
                paths[url_path] = {}
            paths[url_path][method] = operation

        oas3_doc = {
            "openapi": "3.0.3",
            "info": {
                "title": "Imported from Katana",
                "version": "1.0.0",
            },
            "paths": paths,
        }

        output_file = output_dir / "seed.json"
        output_file.write_text(json.dumps(oas3_doc, indent=2), encoding="utf-8")
        return output_file
