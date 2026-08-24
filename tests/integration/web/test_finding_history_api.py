"""Integration tests for GET /api/v1/projects/{project_id}/findings/{id}/history."""

from __future__ import annotations

import pytest

from tests.integration.web.conftest import TEST_PORT

pytestmark = pytest.mark.integration


class TestFindingHistoryAPI:
    async def test_empty_history_for_new_finding(self, app_client) -> None:
        client, finding_id, _, _, _, project_id = app_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["offset"] == 0

    async def test_history_appears_after_patch(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "critical"},
            headers=mut_headers,
        )
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["finding_id"] == finding_id
        assert item["source"] == "web_ui"
        assert "before_values" in item
        assert "after_values" in item

    async def test_multiple_patches_all_recorded(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        for sev in ("critical", "high", "medium"):
            await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": sev},
                headers=mut_headers,
            )
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 3

    async def test_history_ordered_desc_by_timestamp(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        for sev in ("critical", "high"):
            await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": sev},
                headers=mut_headers,
            )
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        items = resp.json()["items"]
        timestamps = [i["timestamp"] for i in items]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_pagination_limit_respected(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        for sev in ("critical", "high", "medium"):
            await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": sev},
                headers=mut_headers,
            )
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history"
            "?limit=2&offset=0",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2
        assert body["limit"] == 2

    async def test_pagination_offset_skips_rows(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        for sev in ("critical", "high", "medium"):
            await client.patch(
                f"/api/v1/projects/{project_id}/findings/{finding_id}",
                json={"severity": sev},
                headers=mut_headers,
            )
        resp_page1 = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history"
            "?limit=2&offset=0",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        resp_page2 = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}/history"
            "?limit=2&offset=2",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        ids_p1 = {i["id"] for i in resp_page1.json()["items"]}
        ids_p2 = {i["id"] for i in resp_page2.json()["items"]}
        assert ids_p1.isdisjoint(ids_p2)

    async def test_unknown_finding_returns_404(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        resp = await client.get(
            f"/api/v1/projects/{project_id}/findings/999999/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 404

    async def test_unknown_project_returns_404(self, app_client) -> None:
        client, finding_id, _, _, _, _ = app_client
        resp = await client.get(
            f"/api/v1/projects/999999/findings/{finding_id}/history",
            headers={"Origin": f"https://127.0.0.1:{TEST_PORT}"},
        )
        assert resp.status_code == 404
