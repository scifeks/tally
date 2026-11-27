"""Unit tests for the retired DefectDojo setting names."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from core.config.schemas.defectdojo_config import (
    DefectDojoGlobalConfig,
    DefectDojoProjectConfig,
)

_CONNECTION = {"url": "http://defectdojo.example.com", "api_token": "t"}


class TestRetiredDefectDojoSettings:
    @pytest.mark.parametrize(
        ("model", "payload", "message"),
        [
            (
                DefectDojoGlobalConfig,
                {**_CONNECTION, "engagement_type": "X"},
                "renamed to engagement_name",
            ),
            (
                DefectDojoGlobalConfig,
                {**_CONNECTION, "product_type": "Tally Scan"},
                "company_name",
            ),
            (
                DefectDojoProjectConfig,
                {"engagement_type": None},
                "renamed to engagement_name",
            ),
        ],
        ids=[
            "global_engagement_type",
            "global_product_type",
            "project_engagement_type",
        ],
    )
    def test_old_name_is_rejected_with_its_replacement(
        self, model: type[BaseModel], payload: dict, message: str
    ) -> None:
        with pytest.raises(ValidationError, match=message):
            model(**payload)

    def test_new_name_is_accepted(self) -> None:
        config = DefectDojoGlobalConfig(
            url="http://defectdojo.example.com",
            api_token="t",
            engagement_name="Audit 2026",
        )

        assert config.engagement_name == "Audit 2026"
