"""Entry point for converting endpoint definition files to OAS3."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import ConverterError
from .detector import FormatDetector
from .har import HARAdapter
from .katana import KatanaAdapter
from .oas2 import OAS2Adapter
from .oas3 import OAS3PassthroughAdapter
from .postman import PostmanAdapter

_ADAPTER_MAP = {
    "oas3": OAS3PassthroughAdapter,
    "oas2": OAS2Adapter,
    "postman": PostmanAdapter,
    "har": HARAdapter,
    "katana": KatanaAdapter,
}


def convert_endpoint_file(
    source_path: Path,
    output_dir: Path,
    originals_dir: Path,
) -> Path:
    """Convert an endpoint definition file to OAS3.

    Validates source_path, backs it up to originals_dir, detects the format,
    validates the content, and delegates to the appropriate adapter for
    conversion. Returns the path to the output file.

    Raises ConverterError if the source is missing, unreadable, invalid,
    or conversion fails.
    """
    if not source_path.exists():
        raise ConverterError(f"Source file does not exist: {source_path}")
    try:
        source_path.read_bytes()
    except OSError as exc:
        raise ConverterError(f"Source file is not readable: {exc}") from exc

    originals_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, originals_dir / source_path.name)

    fmt = FormatDetector().detect(source_path)
    adapter = _ADAPTER_MAP[fmt]()

    adapter.validate(source_path)

    output_dir.mkdir(parents=True, exist_ok=True)

    return adapter.convert(source_path, output_dir)
