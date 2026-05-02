"""PdfRenderer port."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class PdfRenderError(Exception):
    """Raised when a PDF backend fails to render the document."""


@runtime_checkable
class PdfRenderer(Protocol):
    """Render an HTML document with a CSS stylesheet to PDF bytes."""

    def render(self, html: str, css: str) -> bytes: ...
