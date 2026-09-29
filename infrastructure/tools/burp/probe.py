"""Burp REST API availability probe."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from infrastructure.tools.burp.rest_client import (
    BurpRestClient,
)

if TYPE_CHECKING:
    from core.config.schemas.burp_config import BurpConfig

_log = logging.getLogger(__name__)


def probe_burp_availability(
    burp_config: BurpConfig | None,
) -> bool | None:
    """Probe Burp REST API health.

    Returns None (not configured), True (available),
    or False (configured but offline).
    """
    if burp_config is None:
        return None
    client = BurpRestClient(
        burp_config.base_url,
        api_key=burp_config.api_key,
    )
    available = client.health_check()
    if available:
        _log.info(
            "Burp available at %s",
            burp_config.base_url,
        )
    else:
        _log.warning(
            "Burp configured at %s but not reachable",
            burp_config.base_url,
        )
    return available
