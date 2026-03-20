"""GlobalConfig schema."""

from pydantic import BaseModel, Field

from .claude_config import ClaudeConfig
from .ollama_config import OllamaConfig
from .ollama_embedding_config import OllamaEmbeddingConfig


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
    mcp_batch_size: int = Field(default=10, ge=1)
    mcp_batch_timeout_seconds: int = Field(default=30, ge=1)
    mcp_session_timeout_seconds: int = Field(
        default=300, description="Max seconds for a single Claude triage session"
    )
