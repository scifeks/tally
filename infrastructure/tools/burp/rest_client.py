"""Burp Suite REST API client adapter."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from domain.tools.burp.ports import BurpApiError
from infrastructure.tools.burp.models import (
    BurpScanProgress,
    BurpScanRequest,
)

_log = logging.getLogger(__name__)

_HEALTH_CHECK_TIMEOUT = 10.0
_DEFAULT_TIMEOUT = 30.0
_ENTERPRISE_FIELDS = frozenset({"name"})


class BurpRestClient:
    """Driven adapter for Burp Suite's REST API."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def health_check(self) -> bool:
        try:
            resp = httpx.get(
                f"{self._base_url}/v0.1/",
                timeout=_HEALTH_CHECK_TIMEOUT,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def create_scan(self, request: BurpScanRequest) -> str:
        payload = self._serialize_scan_request(request)
        resp = self._post_scan(payload)
        if resp.status_code == 400 and "Enterprise-only" in resp.text:
            stripped = {k: v for k, v in payload.items() if k not in _ENTERPRISE_FIELDS}
            if stripped != payload:
                _log.warning(
                    "Burp returned Enterprise-only error; retrying without fields: %s",
                    _ENTERPRISE_FIELDS & payload.keys(),
                )
                resp = self._post_scan(stripped)
        if resp.status_code != 201:
            raise BurpApiError(
                resp.status_code,
                self._error_text(resp),
            )
        return resp.headers["Location"]

    def _post_scan(self, payload: dict[str, Any]) -> httpx.Response:
        body = json.dumps(payload).encode()
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        return httpx.post(
            f"{self._base_url}/v0.1/scan",
            content=body,
            headers=headers,
            timeout=_DEFAULT_TIMEOUT,
        )

    def get_scan_progress(
        self,
        task_id: str,
        *,
        after: int = 0,
        max_issue_events: int = 100,
    ) -> BurpScanProgress:
        resp = httpx.get(
            f"{self._base_url}/v0.1/scan/{task_id}",
            params={
                "after": after,
                "issue_events": max_issue_events,
            },
            timeout=_DEFAULT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise BurpApiError(
                resp.status_code,
                self._error_text(resp),
            )
        data = resp.json()
        return BurpScanProgress(
            status=data["scan_status"],
            metrics=data.get("scan_metrics", {}),
            issue_events=data.get("issue_events", []),
        )

    @staticmethod
    def _serialize_scan_request(
        request: BurpScanRequest,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"urls": request.urls}
        if request.name is not None:
            payload["name"] = request.name
        if request.scan_configurations:
            payload["scan_configurations"] = [
                {"type": "NamedConfiguration", "name": n}
                for n in request.scan_configurations
            ]
        return payload

    @staticmethod
    def _error_text(resp: httpx.Response) -> str:
        try:
            return str(resp.json())
        except Exception:
            return resp.text
