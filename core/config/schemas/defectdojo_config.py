"""DefectDojo export configuration schema."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ENGAGEMENT_TYPE_RENAMED = "defectdojo.engagement_type was renamed to engagement_name"
_PRODUCT_TYPE_REMOVED = (
    "defectdojo.product_type was removed: the DefectDojo Organization"
    " now comes from the project's company_name"
)


def _reject_retired(data: Any, retired: dict[str, str]) -> Any:
    if isinstance(data, dict):
        for name, message in retired.items():
            if name in data:
                raise ValueError(message)
    return data


class DefectDojoGlobalConfig(BaseModel):
    """DefectDojo server connection and defaults."""

    url: str
    api_token: str
    verify_ssl: bool = Field(default=True)
    engagement_name: str = Field(default="Tally Engagement")
    auto_create_context: bool = Field(default=True)
    scan_type: str = Field(default="Generic Findings Import")

    @model_validator(mode="before")
    @classmethod
    def _reject_retired_settings(cls, data: Any) -> Any:
        return _reject_retired(
            data,
            {
                "engagement_type": _ENGAGEMENT_TYPE_RENAMED,
                "product_type": _PRODUCT_TYPE_REMOVED,
            },
        )


class DefectDojoProjectConfig(BaseModel):
    """DefectDojo project-level overrides."""

    model_config = ConfigDict(extra="ignore")

    engagement_name: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_retired_settings(cls, data: Any) -> Any:
        return _reject_retired(data, {"engagement_type": _ENGAGEMENT_TYPE_RENAMED})
