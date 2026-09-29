from dataclasses import dataclass


@dataclass(frozen=True)
class Capabilities:
    chat_enabled: bool
    triage_enabled: bool
    report_retention_enabled: bool
    max_report_history: int
    triage_backend_label: str | None
    triage_mode: str | None
