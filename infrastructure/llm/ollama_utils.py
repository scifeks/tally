"""Query and verify Ollama availability and models."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def verify_ollama_available(base_url: str) -> bool:
    """Return True if Ollama is reachable at base_url."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def get_ollama_models(base_url: str) -> list[str]:
    """Return a list of model names available in Ollama."""
    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, KeyError, ValueError):
        return []
