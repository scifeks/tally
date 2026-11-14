"""Unit tests for the Burp REST client adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from domain.tools.burp.ports import BurpApiError
from infrastructure.tools.burp.models import BurpScanRequest
from infrastructure.tools.burp.rest_client import BurpRestClient

_MODULE = "infrastructure.tools.burp.rest_client"


class TestHealthCheck:
    def test_returns_true_on_200(self) -> None:
        mock_resp = MagicMock(status_code=200)
        with patch(f"{_MODULE}.httpx.get", return_value=mock_resp):
            client = BurpRestClient("http://localhost:1337")
            assert client.health_check() is True

    def test_returns_false_on_non_200(self) -> None:
        mock_resp = MagicMock(status_code=500)
        with patch(f"{_MODULE}.httpx.get", return_value=mock_resp):
            client = BurpRestClient("http://localhost:1337")
            assert client.health_check() is False

    def test_returns_false_on_connection_error(self) -> None:
        with patch(
            f"{_MODULE}.httpx.get",
            side_effect=httpx.ConnectError("refused"),
        ):
            client = BurpRestClient("http://localhost:1337")
            assert client.health_check() is False

    def test_sends_get_to_api_root(self) -> None:
        mock_resp = MagicMock(status_code=200)
        with patch(f"{_MODULE}.httpx.get", return_value=mock_resp) as mock_get:
            client = BurpRestClient("http://10.1.20.101:1337")
            client.health_check()
            args, kwargs = mock_get.call_args
            assert args[0] == "http://10.1.20.101:1337/v0.1/"


class TestCreateScan:
    def _ok_response(self, task_id: str = "5") -> MagicMock:
        return MagicMock(
            status_code=201,
            headers={"Location": task_id},
        )

    def test_returns_task_id_from_location_header(self) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            return_value=self._ok_response("7"),
        ):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"])
            assert client.create_scan(req) == "7"

    def test_sends_content_length_header(self) -> None:
        with patch(
            f"{_MODULE}.httpx.post",
            return_value=self._ok_response(),
        ) as mock_post:
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"])
            client.create_scan(req)
            _, kwargs = mock_post.call_args
            headers = kwargs.get("headers", {})
            assert "Content-Length" in headers

    def test_post_body_excludes_name_by_default(self) -> None:
        import json

        with patch(
            f"{_MODULE}.httpx.post",
            return_value=self._ok_response(),
        ) as mock_post:
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"])
            client.create_scan(req)
            _, kwargs = mock_post.call_args
            body = json.loads(kwargs["content"])
            assert "name" not in body

    def test_raises_on_non_201(self) -> None:
        mock_resp = MagicMock(
            status_code=400,
            text="Bad Request",
            json=MagicMock(return_value={"error": "bad"}),
        )
        with patch(f"{_MODULE}.httpx.post", return_value=mock_resp):
            client = BurpRestClient("http://localhost:1337")
            req = BurpScanRequest(urls=["https://example.com"])
            with pytest.raises(BurpApiError) as exc_info:
                client.create_scan(req)
            assert exc_info.value.status_code == 400


class TestGetScanProgress:
    def _progress_response(
        self,
        status: str = "crawling",
        metrics: dict | None = None,
        issue_events: list | None = None,
    ) -> MagicMock:
        body = {
            "scan_status": status,
            "scan_metrics": metrics or {},
            "issue_events": issue_events or [],
        }
        return MagicMock(status_code=200, json=MagicMock(return_value=body))

    def test_parses_progress_response(self) -> None:
        resp = self._progress_response(
            status="auditing",
            metrics={"crawl_requests_made": 42},
            issue_events=[{"type": "issue_found"}],
        )
        with patch(f"{_MODULE}.httpx.get", return_value=resp):
            client = BurpRestClient("http://localhost:1337")
            progress = client.get_scan_progress("3")
            assert progress.status == "auditing"
            assert progress.metrics["crawl_requests_made"] == 42
            assert len(progress.issue_events) == 1

    def test_sends_cursor_params(self) -> None:
        with patch(
            f"{_MODULE}.httpx.get",
            return_value=self._progress_response(),
        ) as mock_get:
            client = BurpRestClient("http://localhost:1337")
            client.get_scan_progress("3", after=10, max_issue_events=50)
            _, kwargs = mock_get.call_args
            assert kwargs["params"] == {
                "after": 10,
                "issue_events": 50,
            }

    def test_raises_on_404(self) -> None:
        mock_resp = MagicMock(
            status_code=404,
            text="Task ID not found",
            json=MagicMock(return_value={}),
        )
        with patch(f"{_MODULE}.httpx.get", return_value=mock_resp):
            client = BurpRestClient("http://localhost:1337")
            with pytest.raises(BurpApiError) as exc_info:
                client.get_scan_progress("999")
            assert exc_info.value.status_code == 404
