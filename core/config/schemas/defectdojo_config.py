"""DefectDojo export configuration schema."""

from pydantic import BaseModel, Field


class DefectDojoConnectionConfig(BaseModel):
    """DefectDojo server connection settings."""

    url: str
    api_token: str
    verify_ssl: bool = Field(default=True)


class DefectDojoProjectConfig(BaseModel):
    """DefectDojo targeting settings per project."""

    product_name: str
    engagement_name: str
    product_type_name: str = Field(default="Tally")
    auto_create_context: bool = Field(default=True)
