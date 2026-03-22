"""Dedicated per-field LLM prompt modules.

Each module in this package handles one constrained enrichment field that
requires a field-specific prompt (e.g. an enum table rather than free-form
reasoning). All modules must expose a single function:

    def render_prompt(source_values: dict[str, Any]) -> str: ...

``source_values`` is a dict of pre-extracted metadata key/value pairs for
the finding. The function returns the complete user-turn prompt string; the
system prompt is owned by ``EnrichmentPipeline``.

Adding a new dedicated field:
1. Create ``application/rag/prompts/<field_name>.py`` with ``render_prompt``.
2. Add one entry to ``_DEDICATED_MODULES`` below.
"""

from __future__ import annotations

import importlib
from typing import Any

_DEDICATED_MODULES: dict[str, str] = {
    "owasp_name": "application.rag.prompts.owasp_name",
}


def get_dedicated_prompt(field_name: str, source_values: dict[str, Any]) -> str:
    """Dispatch to the dedicated prompt module for *field_name*.

    Raises:
        KeyError: No dedicated module registered for *field_name*.
        AttributeError: The registered module does not expose ``render_prompt``.
    """
    module_path = _DEDICATED_MODULES[field_name]
    module = importlib.import_module(module_path)
    return module.render_prompt(source_values)  # type: ignore[no-any-return]
