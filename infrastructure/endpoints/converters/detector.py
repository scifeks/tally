"""Format detector for endpoint definition files."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .base import ConverterError

_SUPPORTED_FORMATS = (
    "oas3  — OpenAPI 3.x JSON/YAML (contains 'openapi' key starting with '3.')\n"
    "oas2  — Swagger 2.0 JSON/YAML (contains 'swagger: 2.0' key)\n"
    "postman — Postman collection JSON "
    "(contains 'info.schema' with 'postman/collection')\n"
    "har   — HTTP Archive JSON (file extension .har)\n"
    "katana — Katana crawler JSONL output (file extension .jsonl)"
)


def _parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json" or path.suffix == ".har":
        try:
            result = json.loads(text)
            if not isinstance(result, dict):
                raise ConverterError(
                    f"File does not contain a JSON object: {path.name}"
                )
            return result
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
    try:
        result = yaml.safe_load(text)
        if not isinstance(result, dict):
            raise ConverterError(f"File does not contain a YAML mapping: {path.name}")
        return result
    except yaml.YAMLError as exc:
        raise ConverterError(f"File is not valid YAML: {exc}") from exc


class FormatDetector:
    """Detect the format of an endpoint definition file."""

    def detect(self, path: Path) -> str:
        """Return format name: 'oas3', 'oas2', 'postman', or 'har'.

        Detection order:
        1. Extension check: .har → 'har' immediately
        2. Parse as JSON or YAML
        3. 'openapi' key starting with '3.' → 'oas3'
        4. 'swagger' key equal to '2.0' → 'oas2'
        5. 'info.schema' containing 'postman/collection' → 'postman'
        6. None matched → ConverterError listing supported formats
        """
        if path.suffix == ".har":
            return "har"
        if path.suffix == ".jsonl":
            return "katana"

        doc = _parse_doc(path)

        openapi_ver = doc.get("openapi", "")
        if isinstance(openapi_ver, str) and openapi_ver.startswith("3."):
            return "oas3"

        if doc.get("swagger") == "2.0":
            return "oas2"

        info = doc.get("info", {})
        schema = info.get("schema", "") if isinstance(info, dict) else ""
        if isinstance(schema, str) and "postman/collection" in schema:
            return "postman"

        raise ConverterError(
            f"Could not detect format of {path.name}. "
            f"Supported formats:\n{_SUPPORTED_FORMATS}"
        )
