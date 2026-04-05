"""Abstract base class and error type for endpoint file converters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ConverterError(Exception):
    """Raised for validation failures and conversion errors."""


class ConverterAdapter(ABC):
    """Interface all converter adapters must implement."""

    @property
    @abstractmethod
    def supported_extensions(self) -> frozenset[str]: ...

    @abstractmethod
    def validate(self, path: Path) -> None:
        """Raise ConverterError if file is not valid for this format."""

    @abstractmethod
    def convert(self, source: Path, output_dir: Path) -> Path:
        """Convert source to OAS3. Return path to output file.

        The output file is written inside output_dir.
        Raises ConverterError on failure.
        """
