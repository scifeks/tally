"""GlobalConfig schema."""

from pydantic import BaseModel, Field

from .claude_config import ClaudeConfig
from .ollama_config import OllamaConfig
from .ollama_embedding_config import OllamaEmbeddingConfig

MCP_BATCH_SIZE_DEFAULT: int = 10
MCP_BATCH_TIMEOUT_SECONDS_DEFAULT: int = 30
MCP_SESSION_TIMEOUT_SECONDS_DEFAULT: int = 300


class GlobalConfig(BaseModel):
    """Global application configuration."""

    chat_llm_provider: str = "ollama"
    enrichment_llm_provider: str = "ollama"
    report_llm_provider: str = "ollama"
    embedding_provider: str = "ollama_embedding"
    ollama: OllamaConfig | None = None
    claude: ClaudeConfig | None = None
    ollama_embedding: OllamaEmbeddingConfig | None = None
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
