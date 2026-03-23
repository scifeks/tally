"""PDF renderer strategy — production backend uses WeasyPrint."""

from __future__ import annotations

from abc import ABC, abstractmethod


class PDFRenderError(Exception):
    """Raised when a PDF backend fails to render the document."""


class PDFRenderer(ABC):
    """Strategy interface for PDF rendering backends."""

    @abstractmethod
    def render(self, html: str, css: str) -> bytes:
        """Render *html* with *css* and return the PDF bytes.

        Args:
            html: Complete HTML document string.
            css:  CSS stylesheet string to apply.

        Returns:
            Raw PDF bytes.

        Raises:
            PDFRenderError: The backend failed to produce a PDF.
        """


class WeasyPrintRenderer(PDFRenderer):
    """PDF renderer backed by WeasyPrint.

    WeasyPrint is imported lazily so this module can be imported on systems
    where WeasyPrint is not installed (e.g. CI environments running unit tests
    that mock the backend).
    """

    def render(self, html: str, css: str) -> bytes:
        try:
            import weasyprint  # type: ignore[import-untyped]

            stylesheet = weasyprint.CSS(string=css)
            pdf = weasyprint.HTML(string=html).write_pdf(stylesheets=[stylesheet])
            if pdf is None:
                raise PDFRenderError("write_pdf returned None")
            return pdf
        except PDFRenderError:
            raise
        except Exception as exc:
            raise PDFRenderError(str(exc)) from exc


def get_pdf_renderer(name: str) -> PDFRenderer:
    """Return the PDF renderer for the given backend name.

    Args:
        name: Backend identifier.  Currently ``"weasyprint"`` is the only
              supported value.

    Returns:
        Configured :class:`PDFRenderer` instance.

    Raises:
        ValueError: *name* is not a recognised backend.
    """
    if name == "weasyprint":
        return WeasyPrintRenderer()
    raise ValueError(f"Unknown PDF backend: {name!r}. Supported: 'weasyprint'")
