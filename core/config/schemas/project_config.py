"""ProjectConfig schema."""

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    project_name: str
    created: str
    company_name: str = Field(default="")
    department_name: str = Field(default="")
    abbreviation: str = Field(default="")
