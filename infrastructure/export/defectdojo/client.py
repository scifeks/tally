"""Thin HTTP wrapper for DefectDojo API communication."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_REIMPORT_TIMEOUT = 120.0
_DEFAULT_TIMEOUT = 30.0


class DefectDojoClient:
    def __init__(self, url: str, api_token: str, *, verify_ssl: bool = True) -> None:
        if not url.startswith(("http://", "https://")):
            raise ValueError(
                f"DefectDojo URL must use http:// or https:// scheme, got: {url!r}"
            )
        self._base_url = url.rstrip("/")
        self._headers = {"Authorization": f"Token {api_token}"}
        self._verify_ssl = verify_ssl

    def reimport_scan(
        self,
        json_payload: bytes,
        scan_type: str,
        product_name: str,
        engagement_name: str,
        *,
        product_type_name: str = "Tally Scan",
        auto_create_context: bool = True,
        test_title: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """POST to /api/v2/reimport-scan/.

        Returns (status_code, response_body).
        """
        url = f"{self._base_url}/api/v2/reimport-scan/"
        files = {
            "file": ("findings.json", json_payload, "application/json"),
        }
        data: dict[str, Any] = {
            "scan_type": scan_type,
            "product_name": product_name,
            "engagement_name": engagement_name,
            "product_type_name": product_type_name,
            "auto_create_context": str(auto_create_context),
        }
        if test_title is not None:
            data["test_title"] = test_title
        response = httpx.post(
            url,
            headers=self._headers,
            data=data,
            files=files,
            verify=self._verify_ssl,
            timeout=_REIMPORT_TIMEOUT,
        )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        return response.status_code, body

    def get_product_id(self, product_name: str) -> int | None:
        """Look up a Product by name, return its ID or None."""
        url = f"{self._base_url}/api/v2/products/"
        try:
            response = httpx.get(
                url,
                headers=self._headers,
                params={"name": product_name},
                verify=self._verify_ssl,
                timeout=_DEFAULT_TIMEOUT,
            )
            if response.status_code != 200:
                return None
            results = response.json().get("results", [])
            if not results:
                return None
            return int(results[0]["id"])
        except (httpx.HTTPError, KeyError, ValueError):
            return None

    def create_endpoint(
        self,
        product_id: int,
        protocol: str,
        host: str,
        port: int,
        path: str,
    ) -> tuple[int, dict[str, Any]]:
        """POST to /api/v2/endpoints/."""
        url = f"{self._base_url}/api/v2/endpoints/"
        payload: dict[str, Any] = {
            "product": product_id,
            "protocol": protocol,
            "host": host,
            "port": port,
            "path": path,
        }
        response = httpx.post(
            url,
            headers=self._headers,
            json=payload,
            verify=self._verify_ssl,
            timeout=_DEFAULT_TIMEOUT,
        )
        try:
            body = response.json()
        except Exception:
            body = {"raw": response.text}
        return response.status_code, body

    def test_connection(self) -> bool:
        """GET /api/v2/user_profile/ to verify credentials."""
        url = f"{self._base_url}/api/v2/user_profile/"
        try:
            response = httpx.get(
                url,
                headers=self._headers,
                verify=self._verify_ssl,
                timeout=_DEFAULT_TIMEOUT,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False
