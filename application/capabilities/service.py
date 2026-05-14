from __future__ import annotations

from typing import TYPE_CHECKING

from core.config.manager import ConfigManager
from domain.capabilities.models import Capabilities

if TYPE_CHECKING:
    from application.triage.readiness import TriageReadiness


class CapabilitiesService:
    """Compute SPA-facing feature flags from runtime configuration."""

    def __init__(
        self,
        base_path: str,
        triage_readiness: TriageReadiness,
    ) -> None:
        self._base_path = base_path
        self._triage_readiness = triage_readiness

    def compute(self) -> Capabilities:
        try:
            config = ConfigManager(self._base_path).global_config
            chat_enabled = config.chat_inference is not None
            max_report_history = int(config.report_retention_count or 0)
        except FileNotFoundError:
            chat_enabled = False
            max_report_history = 10

        return Capabilities(
            chat_enabled=chat_enabled,
            triage_enabled=self._triage_readiness.enabled,
            report_retention_enabled=False,
            max_report_history=max_report_history,
        )
