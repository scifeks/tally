"""Enterprise-only field retry logic."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from domain.tools.burp.ports import BurpApiError
from infrastructure.tools.burp.models import BurpScanRequest
from infrastructure.tools.burp.rest_client import BurpRestClient

_MODULE = "infrastructure.tools.burp.rest_client"


def _enterprise_400(field: str = "name") -> MagicMock:
    msg = (
        f"{field.capitalize()}s are not supported in the "
        "desktop product - this is an Enterprise-only feature."
    )
    return MagicMock(
        status_code=400,
        text=msg,
        json=MagicMock(return_value={"error": msg}),
    )


def _created(task_id: str = "1") -> MagicMock:
    return MagicMock(status_code=201, headers={"Location": task_id})


class TestEnterpriseRetry:
    def test_strips_enterprise_field_and_retries(
        self,
    ) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            side_effect=[_enterprise_400(), _created("9")],
        ):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"], name="my-scan")
            task_id = client.create_scan(req)
            assert task_id == "9"

    def test_retry_body_excludes_enterprise_field(
        self,
    ) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            side_effect=[_enterprise_400(), _created()],
        ) as mock_post:
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"], name="my-scan")
            client.create_scan(req)
            retry_call = mock_post.call_args_list[1]
            body = json.loads(retry_call.kwargs["content"])
            assert "name" not in body
            assert body["urls"] == ["https://example.com"]

    def test_non_enterprise_400_raises_immediately(
        self,
    ) -> None:
        resp = MagicMock(
            status_code=400,
            text="invalid urls format",
            json=MagicMock(return_value={"error": "invalid urls format"}),
        )
        with patch(f"{_MODULE}.httpx.post", return_value=resp):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["bad"])
            with pytest.raises(BurpApiError):
                client.create_scan(req)

    def test_retry_still_failing_raises(self) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            side_effect=[
                _enterprise_400(),
                MagicMock(
                    status_code=400,
                    text="other error",
                    json=MagicMock(return_value={"error": "other"}),
                ),
            ],
        ):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"], name="scan")
            with pytest.raises(BurpApiError):
                client.create_scan(req)

    def test_no_enterprise_fields_present_raises(
        self,
    ) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            return_value=_enterprise_400(),
        ):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"])
            with pytest.raises(BurpApiError):
                client.create_scan(req)

    def test_logs_warning_on_retry(self, caplog) -> None:
        import logging

        with (
            caplog.at_level(logging.WARNING),
            patch(
                f"{_MODULE}.httpx.post",
                side_effect=[_enterprise_400(), _created()],
            ),
        ):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"], name="x")
            client.create_scan(req)
        assert any("Enterprise-only" in r.message for r in caplog.records)
