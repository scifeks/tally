"""Helpers for inspecting fenced data in rendered triage prompts."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(
    r"^<<<TALLY_DATA_START: (?P<label>\w+)>>>\n"
    r"(?P<body>.*?)\n"
    r"<<<TALLY_DATA_END: (?P=label)>>>$",
    re.S | re.M,
)


def fenced_record(prompt: str, label: str) -> dict[str, Any]:
    """Decode the JSON object fenced under *label*; fails if absent or repeated."""
    bodies = [m["body"] for m in _FENCE.finditer(prompt) if m["label"] == label]
    assert len(bodies) == 1, f"expected one {label!r} fence, found {len(bodies)}"
    return json.loads(bodies[0])


def unfenced_text(prompt: str) -> str:
    """Return the prompt with every fenced block removed."""
    return _FENCE.sub("", prompt)
