"""Reporting adapter factory functions."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from infrastructure.reporting.jinja2_template_renderer import (
    Jinja2TemplateRenderer,
)
from infrastructure.reporting.weasyprint_pdf_renderer import (
    WeasyPrintPdfRenderer,
)

if TYPE_CHECKING:
    from application.ports.html_template_renderer import (
        HtmlTemplateRenderer,
    )
    from application.ports.pdf_renderer import PdfRenderer


def create_template_renderer(
    templates_dir: Path,
) -> HtmlTemplateRenderer:
    """Create a Jinja2TemplateRenderer."""
    return Jinja2TemplateRenderer(templates_dir)


def create_pdf_renderer() -> PdfRenderer:
    """Create a WeasyPrintPdfRenderer."""
    return WeasyPrintPdfRenderer()
