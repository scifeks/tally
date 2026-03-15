"""Configuration schemas using Pydantic for validation."""

from pydantic import BaseModel, Field, field_validator, model_validator

_VALID_REPO_TYPES: frozenset[str] = frozenset({"library", "api", "ui"})


class NmapProfile(BaseModel):
    """Nmap scan profile configuration."""

    hosts: list[str] = Field(..., description="List of hosts/subnets to scan")
    nmap_args: str = Field(default="", description="Nmap arguments for this profile")


class NmapHostsConfig(BaseModel):
    """Full nmap_hosts.json configuration."""

    profiles: dict[str, NmapProfile] = Field(default_factory=dict)
    excluded_networks: list[str] = Field(default_factory=list)


class DockerContainer(BaseModel):
    """Docker container configuration for a tool."""

    name: str = Field(..., description="Docker container name")
    tool_path: str = Field(..., description="Path to tool binary inside container")


class CommandEntry(BaseModel):
    """Single tool entry in commands.json."""

    type: str = Field(..., description="Tool type: 'repo' or 'api'")
    location: str = Field(..., description="Execution location: 'local' or 'docker'")
    path: str = Field(default="", description="Binary path for local tools")
    container: DockerContainer | None = Field(
        default=None, description="Docker container config"
    )

    @model_validator(mode="after")
    def validate_location_fields(self) -> "CommandEntry":
        if self.location == "docker" and self.container is None:
            raise ValueError("container is required when location is 'docker'")
        if self.location == "local" and not self.path:
            raise ValueError("path is required when location is 'local'")
        return self


class Repository(BaseModel):
    """Repository configuration."""

    name: str = Field(..., description="Repository name")
    type: list[str] = Field(..., description="Repository types (library, api, ui)")
    path: str = Field(default="", description="Filesystem path to repository")
    docker_path: str = Field(
        default="", description="Container mount path for Docker tools"
    )
    container_name: str = Field(
        default="", description="Docker container name for docker-mode tools"
    )
    languages: list[str] = Field(..., description="Programming languages used")
    base_urls: list[str] = Field(default_factory=list, description="API base URLs")

    @field_validator("type")
    @classmethod
    def validate_repo_type(cls, v: list[str]) -> list[str]:
        """Validate repository type values and mutual exclusivity."""
        if not v:
            raise ValueError("At least one repository type is required")
        invalid = set(v) - _VALID_REPO_TYPES
        if invalid:
            sorted_invalid = ", ".join(sorted(invalid))
            raise ValueError(
                f"Invalid type(s): {sorted_invalid}. Valid: library, api, ui"
            )
        if "library" in v and len(v) > 1:
            raise ValueError("'library' cannot be combined with other types")
        return v

    @field_validator("path")
    @classmethod
    def path_must_exist(cls, v: str) -> str:
        """Validate that repository path exists (only when non-empty)."""
        from pathlib import Path

        if v and not Path(v).exists():
            raise ValueError(f"Repository path does not exist: {v}")
        return v

    @model_validator(mode="after")
    def validate_paths(self) -> "Repository":
        if not self.path and not self.docker_path:
            raise ValueError("At least one of 'path' or 'docker_path' must be set")
        if self.docker_path and not self.container_name:
            raise ValueError("'container_name' is required when 'docker_path' is set")
        return self


class EndpointConfig(BaseModel):
    """API endpoint configuration for a repository."""

    format_version: str = Field(default="1.0")
    repo_name: str
    api_type: str = Field(default="rest", description="API type: rest or graphql")
    endpoints: dict[str, list[str]] = Field(
        default_factory=dict, description="HTTP methods mapped to endpoint paths"
    )


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    project_name: str
    created: str
    repositories: list[Repository] = Field(default_factory=list)


class OllamaConfig(BaseModel):
    """Ollama connection and model configuration."""

    base_url: str = "http://localhost:11434"
    model: str
    timeout_seconds: int = 60

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL format is valid."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v.rstrip("/")


class ClaudeConfig(BaseModel):
    """Anthropic Claude API configuration."""

    api_key: str = ""
    model: str = "claude-opus-4-5"
    max_tokens: int = 1024
    timeout_seconds: int = 60


class OllamaEmbeddingConfig(BaseModel):
    """Ollama embedding model configuration."""

    base_url: str = "http://localhost:11434"
    model: str = "nomic-embed-text:latest"
    timeout_seconds: int = 60

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v.rstrip("/")


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
