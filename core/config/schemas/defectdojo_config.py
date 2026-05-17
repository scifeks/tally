"""DefectDojo export configuration schema."""

from pydantic import BaseModel, ConfigDict, Field


class DefectDojoGlobalConfig(BaseModel):
    """DefectDojo server connection and defaults."""

    url: str
    api_token: str
    verify_ssl: bool = Field(default=True)
    product_type: str = Field(default="Tally Scan")
    engagement_type: str = Field(default="Tally Engagement")
    auto_create_context: bool = Field(default=True)
    scan_type: str = Field(default="Generic Findings Import")


class DefectDojoProjectConfig(BaseModel):
    """DefectDojo project-level overrides."""

    model_config = ConfigDict(extra="ignore")

    engagement_type: str | None = None
