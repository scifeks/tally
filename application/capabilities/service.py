from application.runtime.dependency_service import RuntimeDependencyService
from application.triage.readiness import compute_triage_readiness
from core.config.manager import ConfigManager
from domain.capabilities.models import Capabilities


class CapabilitiesService:
    """Compute SPA-facing feature flags.

    Sources:
      - chat_enabled: GlobalConfig.chat_llm_provider == "ollama".
      - triage_enabled: configured triage backend is usable.
      - report_retention_enabled: hardcoded False; no retention sweep
        mechanism exists yet.
      - max_report_history: GlobalConfig.report_retention_count.
    """

    def __init__(
        self,
        base_path: str,
        runtime_service: RuntimeDependencyService,
    ) -> None:
        self._base_path = base_path
        self._runtime_service = runtime_service

    def compute(self) -> Capabilities:
        try:
            config = ConfigManager(self._base_path).global_config
            chat_enabled = config.chat_llm_provider == "ollama"
            max_report_history = int(config.report_retention_count or 0)
        except FileNotFoundError:
            chat_enabled = False
            max_report_history = 10

        triage_enabled = compute_triage_readiness(
            base_path=self._base_path,
            runtime_service=self._runtime_service,
        ).enabled

        return Capabilities(
            chat_enabled=chat_enabled,
            triage_enabled=triage_enabled,
            report_retention_enabled=False,
            max_report_history=max_report_history,
        )
