"""Convert HTTP Archive (HAR) files to OpenAPI 3.x without external tools."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .base import ConverterAdapter, ConverterError


class HARAdapter(ConverterAdapter):
    """Convert HAR files to OAS3 without external tools."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".har"})

    def validate(self, path: Path) -> None:
        """Check that file is a valid HAR document."""
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
        if "log" not in doc:
            raise ConverterError("File does not contain a HAR 'log' key")
        if "entries" not in doc.get("log", {}):
            raise ConverterError("HAR 'log' object does not contain an 'entries' array")

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert HAR entries to an OAS3 JSON document."""
        doc = json.loads(source.read_text(encoding="utf-8"))
        entries = doc["log"]["entries"]

        paths: dict[str, dict] = {}
        seen: set[tuple[str, str]] = set()

        for entry in entries:
            request = entry.get("request", {})
            response = entry.get("response", {})
            method = request.get("method", "GET").lower()
            url = request.get("url", "")
            url_path = urlparse(url).path or "/"
            key = (url_path, method)
            if key in seen:
                continue
            seen.add(key)

            query_params = [
                {
                    "in": "query",
                    "name": qs["name"],
                    "schema": {"type": "string"},
                }
                for qs in request.get("queryString", [])
            ]

            operation: dict = {
                "parameters": query_params,
                "responses": {
                    str(response.get("status", 200)): {"description": "Response"}
                },
            }

            post_data = request.get("postData")
            if post_data:
                mime = post_data.get("mimeType", "application/octet-stream")
                operation["requestBody"] = {
                    "content": {mime: {"schema": {"type": "object"}}}
                }

            if url_path not in paths:
                paths[url_path] = {}
            paths[url_path][method] = operation

        oas3_doc = {
            "openapi": "3.0.3",
            "info": {
                "title": "Imported from HAR",
                "version": "1.0.0",
            },
            "paths": paths,
        }

        output_file = output_dir / "seed.json"
        output_file.write_text(json.dumps(oas3_doc, indent=2), encoding="utf-8")
        return output_file
