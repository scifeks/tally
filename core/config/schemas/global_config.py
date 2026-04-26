"""GlobalConfig schema."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .claude_config import ClaudeConfig
from .ollama_config import OllamaConfig
from .ollama_embedding_config import OllamaEmbeddingConfig

MCP_BATCH_SIZE_DEFAULT: int = 10
MCP_BATCH_TIMEOUT_SECONDS_DEFAULT: int = 30
MCP_SESSION_TIMEOUT_SECONDS_DEFAULT: int = 300

_BANNED_HOSTS = {"0.0.0.0", "::", ""}


class GlobalConfig(BaseModel):
    """Global application configuration."""

    model_config = ConfigDict(extra="ignore")

    chat_llm_provider: str = "ollama"
    enrichment_llm_provider: str = "ollama"
    report_llm_provider: str = "ollama"
    embedding_provider: str = "ollama_embedding"
    ollama: OllamaConfig | None = None
    ollama_report: OllamaConfig | None = None
    ollama_noir: OllamaConfig | None = None
    claude: ClaudeConfig | None = None
    ollama_embedding: OllamaEmbeddingConfig | None = None
    noir_provider: str = ""
    projects_dir: str = Field(default="./projects")
    location_attestation_confirmed: bool = Field(default=False)
    enrichment_max_concurrency: int = Field(default=4)
    mcp_batch_size: int = Field(default=MCP_BATCH_SIZE_DEFAULT, ge=1)
    mcp_batch_timeout_seconds: int = Field(
        default=MCP_BATCH_TIMEOUT_SECONDS_DEFAULT, ge=1
    )
    mcp_session_timeout_seconds: int = Field(
        default=MCP_SESSION_TIMEOUT_SECONDS_DEFAULT,
        description="Max seconds for a single Claude triage session",
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

    # Web UI / dev server
    web_ui_host: str = Field(default="127.0.0.1")
    web_ui_port: int = Field(default=8080)
    web_ui_vite_port: int = Field(default=3000)
    web_ui_allowed_origins: list[str] | None = None

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
        return [f"http://{self.web_ui_host}:{self.web_ui_vite_port}"]
