"""CommandEntry schema."""

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from .docker_container import DockerContainer
from .validation import has_shell_metacharacters


class CommandEntry(BaseModel):
    """Single tool entry in commands.json."""

    type: str = Field(..., description="Tool type: 'repo' or 'api'")
    location: str = Field(
        ...,
        description="Execution location: 'local' or 'docker'",
    )
    path: str = Field(
        default="",
        description="Binary path for local tools",
    )
    container: DockerContainer | None = Field(
        default=None,
        description="Docker container config",
    )

    @field_validator("path")
    @classmethod
    def path_no_metachar(cls, v: str) -> str:
        if v and has_shell_metacharacters(v):
            raise ValueError("path contains a shell metacharacter")
        return v

    @model_validator(mode="after")
    def validate_location_fields(self) -> "CommandEntry":
        if self.location == "docker" and self.container is None:
            raise ValueError("container is required when location is 'docker'")
        if self.location == "local" and not self.path:
            raise ValueError("path is required when location is 'local'")
        return self
