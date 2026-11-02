from __future__ import annotations

from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from domain.capabilities.models import (
    BackgroundModeAvailabilityPayload,
    Capabilities,
)

if TYPE_CHECKING:
    from application.anthropic.mode_availability import BackgroundModeAvailability
    from application.triage.readiness import TriageReadiness


class CapabilitiesService:
    """Compute SPA-facing feature flags from runtime configuration."""

    def __init__(
        self,
        base_path: str,
        triage_readiness: TriageReadiness,
        background_availability: BackgroundModeAvailability | None = None,
    ) -> None:
        self._base_path = base_path
        self._triage_readiness = triage_readiness
        self._background_availability = background_availability

    def compute(self) -> Capabilities:
        try:
            config = ConfigManager(self._base_path).global_config
            chat_enabled = config.chat_inference is not None
            max_report_history = int(config.report_retention_count or 0)
            default_billing = (
                config.claude.default_billing_method if config.claude else None
            )
        except FileNotFoundError:
            chat_enabled = False
            max_report_history = 10
            default_billing = None

        bg_payload: BackgroundModeAvailabilityPayload | None = None
        if self._background_availability is not None:
            avail = self._background_availability
            bg_payload = BackgroundModeAvailabilityPayload(
                oauth_available=avail.oauth_available,
                api_key_available=avail.api_key_available,
                interactive_available=avail.interactive_available,
                oauth_reason=avail.oauth_reason,
                api_key_reason=avail.api_key_reason,
            )

        return Capabilities(
            chat_enabled=chat_enabled,
            triage_enabled=self._triage_readiness.enabled,
            report_retention_enabled=False,
            max_report_history=max_report_history,
            triage_backend_label=self._triage_readiness.backend_label,
            triage_mode=self._triage_readiness.triage_mode,
            background_mode=bg_payload,
            default_billing_method=default_billing,
        )
