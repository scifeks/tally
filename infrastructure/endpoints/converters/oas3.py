"""OAS3 passthrough adapter — copies valid OAS3 files as-is."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from openapi_spec_validator import OpenAPIV30SpecValidator, validate

from .base import ConverterAdapter, ConverterError


def _parse_file(path: Path) -> dict:
    """Parse a JSON or YAML file and return the parsed dict."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConverterError(f"File is not valid YAML: {exc}") from exc


class OAS3PassthroughAdapter(ConverterAdapter):
    """Adapter for files already in OAS3 format — validates and copies."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json", ".yaml", ".yml"})

    def validate(self, path: Path) -> None:
        """Parse and validate an OAS3 file using openapi-spec-validator."""
        doc = _parse_file(path)
        openapi_ver = doc.get("openapi", "")
        if not isinstance(openapi_ver, str) or not openapi_ver.startswith("3."):
            raise ConverterError(
                f"File does not contain a valid OAS3 'openapi' key "
                f"(found: {openapi_ver!r})"
            )
        try:
            validate(doc, cls=OpenAPIV30SpecValidator)
        except Exception as exc:
            raise ConverterError(f"OAS3 spec validation failed: {exc}") from exc

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Copy source file to output_dir/endpoints<suffix>."""
        dest = output_dir / f"endpoints{source.suffix}"
        shutil.copy2(source, dest)
        return dest
