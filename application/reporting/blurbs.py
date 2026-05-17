"""Blurb loader for pre-written report text fragments."""

from __future__ import annotations

import re
from pathlib import Path

_BLURBS_DIR = Path(__file__).parent / "blurbs"

TESTING_TYPES: dict[str, str] = {
    "white_box": (
        "The assessor was provided with full access to source code, architecture "
        "documentation, and internal system credentials. This approach maximizes "
        "coverage and allows for deep analysis of logic flaws, insecure "
        "configurations, and code-level vulnerabilities that are not visible from "
        "the outside."
    ),
    "grey_box": (
        "The assessor was provided with partial knowledge of the target environment, "
        "such as user-level credentials and high-level architecture diagrams, but "
        "without access to source code. This approach simulates a realistic threat "
        "actor who has gained limited insider knowledge through reconnaissance or "
        "credential theft."
    ),
    "black_box": (
        "The assessor was given no prior knowledge of the target environment and "
        "operated solely from a network or application endpoint perspective. This "
        "approach simulates an external attacker with no privileged access and "
        "focuses on externally exploitable vulnerabilities."
    ),
}


class BlurbNotFoundError(FileNotFoundError):
    """Raised when the requested blurb file does not exist."""


class BlurbVariableError(KeyError):
    """Raised when a placeholder in the blurb has no matching key in variables."""


def load_blurb(name: str, variables: dict[str, str] | None = None) -> str:
    """Load a blurb file and substitute ``{{variable_name}}`` placeholders.

    Raises:
        BlurbNotFoundError: The blurb file does not exist.
        BlurbVariableError: A placeholder in the file has no matching key.
    """
    if variables is None:
        variables = {}

    blurb_path = _BLURBS_DIR / f"{name}.md"
    if not blurb_path.exists():
        raise BlurbNotFoundError(f"Blurb not found: {name!r} (looked in {_BLURBS_DIR})")

    text = blurb_path.read_text(encoding="utf-8")

    placeholders = re.findall(r"\{\{(\w+)\}\}", text)
    missing = [p for p in placeholders if p not in variables]
    if missing:
        raise BlurbVariableError(
            f"Blurb {name!r} references undefined variables: {missing}"
        )

    for key, value in variables.items():
        text = text.replace(f"{{{{{key}}}}}", value)

    return text
