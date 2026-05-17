from __future__ import annotations

from pathlib import Path
from typing import Protocol


class EndpointConverterPort(Protocol):
    def convert(self, source: Path, output_dir: Path) -> Path: ...
