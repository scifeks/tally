"""ProjectConfig schema."""

from pydantic import BaseModel, Field

from .repository import Repository


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    project_name: str
    created: str
    repositories: list[Repository] = Field(default_factory=list)
