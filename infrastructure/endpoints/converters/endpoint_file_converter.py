"""EndpointFileConverter: UrlSourceConverterPort over convert_endpoint_file."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from infrastructure.endpoints.converters import service as _service


class EndpointFileConverter:
    """Convert any supported endpoint file format to an OAS3 dict.

    Delegates to convert_endpoint_file using a private temporary
    directory and reads the produced OAS3 file back into memory.
    """

    def to_oas3(self, source_path: Path) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_dir = tmp_path / "out"
            originals_dir = tmp_path / "originals"
            oas3_path = _service.convert_endpoint_file(
                source_path, out_dir, originals_dir
            )
            return json.loads(oas3_path.read_text(encoding="utf-8"))
