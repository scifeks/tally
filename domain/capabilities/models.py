from dataclasses import dataclass


@dataclass(frozen=True)
class BackgroundModeAvailabilityPayload:
    """SPA-facing projection of background-mode credential availability."""

    oauth_available: bool
    api_key_available: bool
    interactive_available: bool
    oauth_reason: str | None = None
    api_key_reason: str | None = None


@dataclass(frozen=True)
class Capabilities:
    chat_enabled: bool
    triage_enabled: bool
    report_retention_enabled: bool
    max_report_history: int
    triage_backend_label: str | None
    triage_mode: str | None
    background_mode: BackgroundModeAvailabilityPayload | None = None
    default_billing_method: str | None = None
