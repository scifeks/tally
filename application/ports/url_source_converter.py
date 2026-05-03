"""Port for converting user-uploaded endpoint files to OAS3.

Adapters:
  infrastructure/endpoints/converters/endpoint_file_converter.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class UrlSourceConverterPort(Protocol):
    """Convert a user-uploaded endpoint file to an OAS3 document.

    Implementations may be format-aware (HAR, Postman, OAS2, OAS3,
    Katana JSONL) and own any temporary files needed during conversion.
    """

    def to_oas3(self, source_path: Path) -> dict[str, Any]:
        """Return the parsed OAS3 document for source_path."""
        ...
