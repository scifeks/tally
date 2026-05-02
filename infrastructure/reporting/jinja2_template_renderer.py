"""Jinja2-backed HtmlTemplateRenderer adapter."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import jinja2


class Jinja2TemplateRenderer:
    """HtmlTemplateRenderer backed by Jinja2 with a filesystem loader.

    The Environment is built once at construction. Autoescape is on; all
    template variables are HTML-escaped. Use the ``| safe`` filter inside
    a template for fragments that have already been sanitised.
    """

    def __init__(self, templates_dir: Path) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(templates_dir)),
            autoescape=True,
            keep_trailing_newline=True,
        )

    def render(self, template_name: str, context: Mapping[str, object]) -> str:
        template = self._env.get_template(template_name)
        return template.render(**context)
