"""Postman collection adapter — converts to OAS3 via postman-to-openapi."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .base import ConverterAdapter, ConverterError

_NODE_MISSING_MSG = (
    "Postman collection conversion requires Node.js and npx. "
    "Install Node.js from https://nodejs.org/, then run: "
    "npx postman-to-openapi --help to confirm the tool is available."
)


class PostmanAdapter(ConverterAdapter):
    """Adapter for Postman collections — converts to OAS3."""

    @property
    def supported_extensions(self) -> frozenset[str]:
        return frozenset({".json"})

    def validate(self, path: Path) -> None:
        """Check that file is a Postman collection."""
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConverterError(f"File is not valid JSON: {exc}") from exc
        info = doc.get("info", {})
        schema = info.get("schema", "") if isinstance(info, dict) else ""
        if "postman/collection" not in schema:
            raise ConverterError(
                "File does not appear to be a Postman collection "
                "(expected 'info.schema' to contain 'postman/collection')"
            )

    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert Postman collection to OAS3 using postman-to-openapi."""
        if not shutil.which("node") or not shutil.which("npx"):
            raise ConverterError(_NODE_MISSING_MSG)
        output_file = output_dir / "endpoints.json"
        result = subprocess.run(
            [
                "npx",
                "postman-to-openapi",
                str(source),
                "-f",
                str(output_file),
                "-o",
                "openapi3",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ConverterError(result.stderr)
        return output_file
