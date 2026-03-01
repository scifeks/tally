"""Configuration schemas using Pydantic for validation."""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field, field_validator


class NmapProfile(BaseModel):
    """Nmap scan profile configuration."""
    hosts: List[str] = Field(..., description="List of hosts/subnets to scan")
    nmap_args: str = Field(..., description="Nmap arguments for this profile")


class Repository(BaseModel):
    """Repository configuration."""
    name: str = Field(..., description="Repository name")
    path: str = Field(..., description="Filesystem path to repository")
    languages: List[str] = Field(..., description="Programming languages used")
    base_urls: List[str] = Field(default_factory=list, description="API base URLs")

    @field_validator('path')
    @classmethod
    def path_must_exist(cls, v: str) -> str:
        """Validate that repository path exists."""
        from pathlib import Path
        if not Path(v).exists():
            raise ValueError(f"Repository path does not exist: {v}")
        return v


class EndpointConfig(BaseModel):
    """API endpoint configuration for a repository."""
    format_version: str = Field(default="1.0")
    repo_name: str
    api_type: str = Field(default="rest", description="API type: rest or graphql")
    endpoints: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="HTTP methods mapped to endpoint paths"
    )


class ProjectConfig(BaseModel):
    """Project-level configuration."""
    project_name: str
    created: str
    repositories: List[Repository] = Field(default_factory=list)


class GlobalConfig(BaseModel):
    """Global application configuration."""
    ollama_base_url: str = Field(default="http://localhost:11434")
    default_llm: str = Field(description="Ollama chat model to use (e.g. qwen3:14b)")
    default_embedding: str = Field(description="Ollama embedding model to use (e.g. nomic-embed-text)")
    projects_dir: str = Field(default="./projects")

    @field_validator('ollama_base_url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Ensure URL format is valid."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError("Ollama URL must start with http:// or https://")
        return v.rstrip('/')
