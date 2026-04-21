"""OAS2/Swagger adapter — converts Swagger 2.0 to OAS3 via swagger2openapi."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import yaml

from .base import ConverterAdapter, ConverterError

_NODE_MISSING_MSG = (
    "OAS2/Swagger conversion requires Node.js and npx. Install Node.js "
    "from https://nodejs.org/, then run: npx swagger2openapi --help "
    "to confirm the tool is available."
)


def _parse_file(path: Path) -> dict:
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


class OAS2Adapter(ConverterAdapter):
    """Adapter for Swagger 2.0 files — converts to OAS3 via swagger2openapi."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json", ".yaml", ".yml"})

    def validate(self, path: Path) -> None:
        """Check that file contains a Swagger 2.0 document."""
        doc = _parse_file(path)
        if doc.get("swagger") != "2.0":
            raise ConverterError(
                "File does not contain a Swagger 2.0 document "
                "(expected 'swagger: \"2.0\"' key)"
            )

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert Swagger 2.0 source to OAS3 using swagger2openapi."""
        if not shutil.which("node") or not shutil.which("npx"):
            raise ConverterError(_NODE_MISSING_MSG)
        output_file = output_dir / "seed.json"
        result = subprocess.run(
            ["npx", "swagger2openapi", str(source), "-o", str(output_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ConverterError(result.stderr)
        return output_file
