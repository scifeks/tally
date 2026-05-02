"""HtmlTemplateRenderer port."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class HtmlTemplateRenderer(Protocol):
    """Render a named HTML template against a context mapping."""

    def render(self, template_name: str, context: Mapping[str, object]) -> str: ...
