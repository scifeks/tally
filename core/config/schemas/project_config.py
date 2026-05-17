"""ProjectConfig schema."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .defectdojo_config import DefectDojoProjectConfig


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    project_name: str
    created: str
    company_name: str = Field(default="")
    department_name: str = Field(default="")
    abbreviation: str = Field(default="")
    defectdojo: DefectDojoProjectConfig | None = None
