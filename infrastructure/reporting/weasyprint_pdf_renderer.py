"""WeasyPrint-backed PdfRenderer adapter."""

from __future__ import annotations

from application.ports.pdf_renderer import PdfRenderError


class WeasyPrintPdfRenderer:
    """PdfRenderer backed by WeasyPrint.

    WeasyPrint is imported lazily inside ``render`` so this module can be
    imported on systems without WeasyPrint installed (CI environments
    running unit tests that mock the backend via
    ``patch.dict("sys.modules", {"weasyprint": ...})``).
    """

    def render(self, html: str, css: str) -> bytes:
        try:
            import weasyprint  # type: ignore[import-untyped]

            stylesheet = weasyprint.CSS(string=css)
            pdf = weasyprint.HTML(string=html).write_pdf(stylesheets=[stylesheet])
            if pdf is None:
                raise PdfRenderError("write_pdf returned None")
            return pdf
        except PdfRenderError:
            raise
        except Exception as exc:
            raise PdfRenderError(str(exc)) from exc
