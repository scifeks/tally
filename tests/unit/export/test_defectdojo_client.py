"""Unit tests for the DefectDojo client's Engagement type call."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from infrastructure.export.defectdojo.client import DefectDojoClient

_PATCH = "infrastructure.export.defectdojo.client.httpx.patch"


def _client() -> DefectDojoClient:
    return DefectDojoClient(
        url="http://defectdojo.example.com", api_token="t", verify_ssl=True
    )


class TestSetEngagementType:
    def test_patches_the_engagement_with_the_type(self) -> None:
        with patch(_PATCH, return_value=MagicMock(status_code=200)) as http_patch:
            ok = _client().set_engagement_type(7, "Interactive")

        assert ok is True
        assert http_patch.call_args.args[0] == (
            "http://defectdojo.example.com/api/v2/engagements/7/"
        )
        assert http_patch.call_args.kwargs["json"] == {"engagement_type": "Interactive"}

    @pytest.mark.parametrize(
        "patch_kwargs",
        [
            {"return_value": MagicMock(status_code=403)},
            {"side_effect": httpx.ConnectError("down")},
        ],
        ids=["refused", "unreachable"],
    )
    def test_failure_returns_false_and_does_not_raise(
        self, patch_kwargs: dict[str, Any]
    ) -> None:
        with patch(_PATCH, **patch_kwargs):
            assert _client().set_engagement_type(7, "Interactive") is False
