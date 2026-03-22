"""Unit tests for application.reporting.pdf."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from application.reporting.pdf import (  # noqa: E402
    PDFRenderer,
    PDFRenderError,
    WeasyPrintRenderer,
    get_pdf_renderer,
)

_HTML = "<html><body><p>Test</p></body></html>"
_CSS = "body { font-family: Arial; }"


class TestGetPdfRenderer:
    def test_weasyprint_returns_weasyprint_renderer(self) -> None:
        renderer = get_pdf_renderer("weasyprint")
        assert isinstance(renderer, WeasyPrintRenderer)

    def test_unknown_backend_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="Unknown PDF backend"):
            get_pdf_renderer("unknown_backend")

    def test_renderer_is_abstract_base(self) -> None:
        assert issubclass(WeasyPrintRenderer, PDFRenderer)


class TestWeasyPrintRenderer:
    def test_successful_render_returns_bytes(self) -> None:
        fake_pdf = b"%PDF-1.4 fake"
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value.write_pdf.return_value = fake_pdf
        mock_weasyprint.CSS.return_value = MagicMock()

        with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
            renderer = WeasyPrintRenderer()
            result = renderer.render(_HTML, _CSS)

        assert result == fake_pdf
        assert isinstance(result, bytes)

    def test_weasyprint_failure_raises_pdf_render_error(self) -> None:
        mock_weasyprint = MagicMock()
        mock_weasyprint.HTML.return_value.write_pdf.side_effect = RuntimeError(
            "weasyprint exploded"
        )
        mock_weasyprint.CSS.return_value = MagicMock()

        with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
            renderer = WeasyPrintRenderer()
            with pytest.raises(PDFRenderError, match="weasyprint exploded"):
                renderer.render(_HTML, _CSS)

    def test_css_passed_as_stylesheet(self) -> None:
        fake_pdf = b"%PDF"
        mock_weasyprint = MagicMock()
        mock_css_obj = MagicMock()
        mock_weasyprint.CSS.return_value = mock_css_obj
        mock_weasyprint.HTML.return_value.write_pdf.return_value = fake_pdf

        with patch.dict("sys.modules", {"weasyprint": mock_weasyprint}):
            WeasyPrintRenderer().render(_HTML, _CSS)

        mock_weasyprint.CSS.assert_called_once_with(string=_CSS)
        mock_weasyprint.HTML.return_value.write_pdf.assert_called_once_with(
            stylesheets=[mock_css_obj]
        )
