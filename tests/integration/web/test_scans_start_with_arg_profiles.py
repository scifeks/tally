"""Integration tests for slice 4.8 (additive ``argProfileIds`` on POST /scans).

Covers the contract from ``endpoints.md`` section 5.1: an existing caller
that omits the field still gets a 202; a known profile id flows through
to ``ScanService.start_scan``; an unknown profile id surfaces as a 422
with ``details.fields[].field == "argProfileIds[i]"``.
"""

from __future__ import annotations

from typing import Any

import pytest

from application.locking import get_registry
from application.tools.scan_run_registry import get_scan_run_registry
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _reset_scan_state():
    """Reset process-singleton scan state between tests."""
    get_scan_run_registry().reset()
    reg = get_registry()
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]
    yield
    get_scan_run_registry().reset()
    if reg._jobs.get("scan") is not None:  # type: ignore[attr-defined]
        reg._jobs["scan"] = None  # type: ignore[attr-defined,index]


class TestStartScanArgProfiles:
    @pytest.mark.asyncio
    async def test_start_scan_omits_arg_profile_ids_returns_202(
        self, app_client, monkeypatch
    ) -> None:
        """Omitting the new field defaults to ``[]`` and the scan still starts."""
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={"repoIds": [], "toolIds": [], "domains": []},
            headers=mut_headers,
        )

        assert resp.status_code == 202, resp.text
        assert len(spawned) == 1

    @pytest.mark.asyncio
    async def test_start_scan_with_known_arg_profile_id_returns_202(
        self, app_client, monkeypatch
    ) -> None:
        """A seeded profile id passes route validation and reaches the service."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        profile_id = ToolArgProfilesRepository(factory).insert(
            tool_name="gitleaks",
            name="verbose",
            args=[],
        )
        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "repoIds": [],
                "toolIds": [],
                "domains": [],
                "argProfileIds": [profile_id],
            },
            headers=mut_headers,
        )

        assert resp.status_code == 202, resp.text
        assert len(spawned) == 1

    @pytest.mark.asyncio
    async def test_start_scan_with_unknown_arg_profile_id_returns_422(
        self, app_client, monkeypatch
    ) -> None:
        """Unknown profile id yields a 422 with the indexed-field envelope."""
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/scans",
            json={
                "repoIds": [],
                "toolIds": [],
                "domains": [],
                "argProfileIds": [999],
            },
            headers=mut_headers,
        )

        assert resp.status_code == 422
        body = resp.json()
        assert body["error"]["code"] == "VALIDATION_ERROR"
        fields = body["error"]["details"]["fields"]
        assert any(entry["field"] == "argProfileIds[0]" for entry in fields)
