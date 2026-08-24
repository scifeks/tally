"""URL canonicalization helpers.

This shim preserves the old import path for infrastructure consumers.
"""

from domain.url_inventory.normalise import normalise_url as _normalise_url

__all__ = ["_normalise_url"]
