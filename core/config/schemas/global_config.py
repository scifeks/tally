"""GlobalConfig schema."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .claude_config import ClaudeConfig
from .defectdojo_config import DefectDojoGlobalConfig
from .feature_inference_config import FeatureInferenceConfig
from .local_inference_config import LocalInferenceConfig
from .openai_config import OpenAIConfig
from .opencode_config import OpenCodeConfig
from .voyage_config import VoyageConfig

TRIAGE_SESSION_TIMEOUT_SECONDS_DEFAULT: int = 300

_BANNED_HOSTS = {"0.0.0.0", "::", ""}


class GlobalConfig(BaseModel):
    """Global application configuration."""

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_llm_keys(cls, data: dict) -> dict:  # type: ignore[override]
        """Convert old flat ``*_llm_provider`` keys to ``*_inference`` objects."""
        if not isinstance(data, dict):
            return data
        _LEGACY = {
            "chat_llm_provider": "chat_inference",
            "enrichment_llm_provider": "enrichment_inference",
            "report_llm_provider": "report_inference",
            "embedding_provider": "embedding_inference",
        }
        for old_key, new_key in _LEGACY.items():
            if old_key in data and new_key not in data:
                value = data.pop(old_key)
                if value:
                    data[new_key] = {"provider": value}
        return data

    triage_agent_provider: Literal["", "claude_code", "open_code"] = ""
    ollama: LocalInferenceConfig | None = None
    llama_cpp: LocalInferenceConfig | None = None
    claude: ClaudeConfig | None = None
    openai: OpenAIConfig | None = None
    voyage: VoyageConfig | None = None
    defectdojo: DefectDojoGlobalConfig | None = None
    opencode: OpenCodeConfig | None = None
    chat_inference: FeatureInferenceConfig | None = None
    enrichment_inference: FeatureInferenceConfig | None = None
    report_inference: FeatureInferenceConfig | None = None
    noir_inference: FeatureInferenceConfig | None = None
    embedding_inference: FeatureInferenceConfig | None = None
    triage_inference: FeatureInferenceConfig | None = None
    antares_inference: FeatureInferenceConfig | None = None
    antares_sweep_config: dict[str, Any] | None = None
    projects_dir: str = Field(default="./projects")
    location_attestation_confirmed: bool = Field(default=False)
    enrichment_max_concurrency: int = Field(default=4)
    triage_session_timeout_seconds: int = Field(
        default=TRIAGE_SESSION_TIMEOUT_SECONDS_DEFAULT,
        description=("Max seconds for a single triage session"),
    )
    report_finding_prefix: str = Field(default="TAL")
    report_retention_count: int = Field(
        default=10,
        ge=0,
        description=(
            "Maximum non-pinned reports retained per project; "
            "older artifacts are deleted after each successful generation. "
            "Set to 0 to disable retention sweeping."
        ),
    )
    chat_session_retention_count: int = Field(
        default=20,
        ge=0,
        description=(
            "Maximum expired chat sessions retained per project; "
            "older sessions (and their messages) are deleted after each "
            "scan-triggered sealing. Set to 0 to disable retention sweeping."
        ),
    )

    # Post-action sync hooks
    post_scan_sync: list[str] = Field(default_factory=list)
    post_triage_sync: list[str] = Field(default_factory=list)

    blind_xss_callback_url: str = Field(
        default="",
        description=(
            "Blind XSS callback URL. Passed to Dalfox via -b and "
            "enables XSStrike --blind mode when non-empty."
        ),
    )

    # Web UI / dev server
    web_ui_host: str = Field(default="127.0.0.1")
    web_ui_port: int = Field(default=8080)
    web_ui_vite_port: int = Field(default=3000)
    web_ui_allowed_origins: list[str] | None = None

    # MCP server
    mcp_port: int = Field(default=8765)

    @field_validator("blind_xss_callback_url")
    @classmethod
    def _validate_xss_callback_url(cls, v: str) -> str:
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(
                "blind_xss_callback_url must start with http:// or https://"
            )
        return v

    @field_validator("web_ui_host")
    @classmethod
    def _reject_wildcard_host(cls, v: str) -> str:
        if v in _BANNED_HOSTS:
            raise ValueError(
                f"web_ui_host {v!r} would bind to all interfaces; "
                "use an explicit IP or hostname (e.g. '127.0.0.1')"
            )
        return v

    @property
    def effective_allowed_origins(self) -> list[str]:
        """Allowed CORS origins: explicit list or derived from host + vite port."""
        if self.web_ui_allowed_origins:
            return list(self.web_ui_allowed_origins)
        return [f"https://{self.web_ui_host}:{self.web_ui_vite_port}"]


GlobalConfig.model_rebuild()
