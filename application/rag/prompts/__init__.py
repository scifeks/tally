"""Dedicated per-field LLM prompt modules.

Each module handles one constrained enrichment field and must expose
render_prompt(source_values: dict[str, Any]) -> str.
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
