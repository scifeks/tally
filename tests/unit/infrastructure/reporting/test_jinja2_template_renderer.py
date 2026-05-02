"""Unit tests for infrastructure.reporting.jinja2_template_renderer."""

from __future__ import annotations

import sys
from pathlib import Path

import jinja2
import pytest

_TALLY_ROOT = Path(__file__).resolve().parents[4]
if str(_TALLY_ROOT) not in sys.path:
    sys.path.insert(0, str(_TALLY_ROOT))

from infrastructure.reporting.jinja2_template_renderer import (  # noqa: E402
    Jinja2TemplateRenderer,
)


class TestJinja2TemplateRenderer:
    def test_render_returns_template_output(self, tmp_path: Path) -> None:
        (tmp_path / "hello.html.j2").write_text("Hello, {{ name }}!", encoding="utf-8")
        renderer = Jinja2TemplateRenderer(tmp_path)

        result = renderer.render("hello.html.j2", {"name": "world"})

        assert result == "Hello, world!"

    def test_autoescape_html_escapes_variables(self, tmp_path: Path) -> None:
        (tmp_path / "esc.html.j2").write_text("{{ payload }}", encoding="utf-8")
        renderer = Jinja2TemplateRenderer(tmp_path)

        result = renderer.render("esc.html.j2", {"payload": "<script>"})

        assert result == "&lt;script&gt;"

    def test_missing_template_raises_template_not_found(self, tmp_path: Path) -> None:
        renderer = Jinja2TemplateRenderer(tmp_path)

        with pytest.raises(jinja2.TemplateNotFound):
            renderer.render("does_not_exist.html.j2", {})

    def test_keep_trailing_newline_is_preserved(self, tmp_path: Path) -> None:
        (tmp_path / "trailing.html.j2").write_text("line\n", encoding="utf-8")
        renderer = Jinja2TemplateRenderer(tmp_path)

        assert renderer.render("trailing.html.j2", {}) == "line\n"
