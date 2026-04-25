"""Tests for GET and PATCH /api/v1/projects/{project_id}/findings endpoints."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


class TestAuthMiddlewareScope:
    async def test_non_api_path_does_not_require_session(self, app_client) -> None:
        """Browser must load the SPA without session cookies.

        Middleware must only enforce session auth on /api/* routes. A GET
        to the SPA root must not return 401 — the browser needs index.html
        to load before it can complete the handshake exchange.
        """
        client, _, _, _, _, _ = app_client
        response = await client.get("/")
        assert response.status_code != 401


class TestGetFindings:
    async def test_type_flags_stripped_from_meta(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings")
        assert response.status_code == 200
        data = response.json()
        findings = data["items"]
        assert len(findings) >= 1
        meta = findings[0]["meta"]
        assert not any(k.startswith("type_") for k in meta)
        assert "profile" in meta

    async def test_list_returns_envelope(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert data["offset"] == 0
        assert data["limit"] == 50
        assert data["total"] >= 1
        assert len(data["items"]) == data["total"]

    async def test_pagination_limit(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?offset=0&limit=1"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] >= 1
        assert data["offset"] == 0
        assert data["limit"] == 1

    async def test_offset_beyond_total_returns_empty_items(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?offset=9999&limit=50"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] >= 1

    async def test_limit_exceeds_max_returns_422(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings?limit=501")
        assert response.status_code == 422

    async def test_negative_offset_returns_422(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings?offset=-1")
        assert response.status_code == 422

    async def test_filter_total_reflects_filtered_set(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?tool=semgrep"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["tool"] == "semgrep" for item in data["items"])

        response_no_match = await client.get(
            f"/api/v1/projects/{project_id}/findings?tool=nonexistent_tool"
        )
        assert response_no_match.status_code == 200
        no_match = response_no_match.json()
        assert no_match["total"] == 0
        assert no_match["items"] == []

    async def test_severity_filter_valid(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?severity=high"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(item["severity"] == "high" for item in data["items"])

    async def test_severity_filter_invalid_returns_422(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?severity=extreme"
        )
        assert response.status_code == 422

    async def test_search_matches_substring(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?search=SQL+injection"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

        response_no_match = await client.get(
            f"/api/v1/projects/{project_id}/findings?search=zzznomatch"
        )
        assert response_no_match.status_code == 200
        assert response_no_match.json()["total"] == 0

    async def test_sort_by_severity_asc(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings?sort=severity&order=asc"
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data

    async def test_unknown_project_returns_404(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/projects/99999/findings")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    async def test_flat_findings_path_is_gone(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/findings/")
        assert response.status_code == 404

    async def test_get_by_id_returns_404_for_unknown(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/99999")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    async def test_get_by_id_returns_correct_finding(self, app_client) -> None:
        client, finding_id, _, _, _, project_id = app_client
        response = await client.get(
            f"/api/v1/projects/{project_id}/findings/{finding_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == finding_id
        assert data["tool"] == "semgrep"
        assert data["severity"] == "high"
        assert data["domain"] == "code"


class TestFindingsCounts:
    async def test_counts_returns_five_buckets(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/counts")
        assert response.status_code == 200
        data = response.json()
        assert "by_severity" in data
        assert "by_domain" in data
        assert "by_segment" in data
        assert "by_repo" in data
        assert "by_status" in data

    async def test_counts_severity_uses_labels(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/counts")
        assert response.status_code == 200
        by_severity = response.json()["by_severity"]
        for label in by_severity:
            assert label in (
                "critical",
                "high",
                "medium",
                "low",
                "informational",
            ), f"unexpected severity label: {label!r}"

    async def test_counts_totals_match_findings(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        list_resp = await client.get(f"/api/v1/projects/{project_id}/findings")
        total = list_resp.json()["total"]

        counts_resp = await client.get(f"/api/v1/projects/{project_id}/findings/counts")
        by_severity = counts_resp.json()["by_severity"]
        assert sum(by_severity.values()) == total

    async def test_counts_unknown_project_returns_404(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/projects/99999/findings/counts")
        assert response.status_code == 404


class TestFindingsFacets:
    async def test_facets_returns_expected_keys(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/facets")
        assert response.status_code == 200
        data = response.json()
        for key in (
            "domains",
            "severities",
            "statuses",
            "confidence_levels",
            "finding_types",
            "tools",
            "repos",
            "segments",
        ):
            assert key in data, f"missing facet key: {key!r}"

    async def test_facets_lists_are_sorted(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/facets")
        data = response.json()
        assert data["tools"] == sorted(data["tools"])
        assert data["repos"] == sorted(data["repos"])

    async def test_facets_tools_includes_seeded_tool(self, app_client) -> None:
        client, _, _, _, _, project_id = app_client
        response = await client.get(f"/api/v1/projects/{project_id}/findings/facets")
        assert "semgrep" in response.json()["tools"]

    async def test_facets_unknown_project_returns_404(self, app_client) -> None:
        client, _, _, _, _, _ = app_client
        response = await client.get("/api/v1/projects/99999/findings/facets")
        assert response.status_code == 404


class TestPatchFinding:
    async def test_patch_updates_editable_field(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "critical"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert response.json()["severity"] == "critical"
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT severity FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert row["severity"] == 0

    async def test_patch_sets_triaged_by_analyst_web(self, app_client) -> None:
        client, finding_id, _, factory, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"status": "false_positive"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        with factory.connect() as conn:
            row = conn.execute(
                "SELECT triaged_by, triaged_at FROM findings WHERE id = ?",
                (finding_id,),
            ).fetchone()
        assert row["triaged_by"] == "analyst_web"
        assert row["triaged_at"] is not None

    async def test_chroma_sync_is_attempted(self, app_client) -> None:
        client, finding_id, rag_mock, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_upserts_on_severity_change(self, app_client) -> None:
        client, finding_id, rag_mock, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_upserts_on_should_report_change(
        self, app_client
    ) -> None:
        client, finding_id, rag_mock, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"should_report": True},
            headers=mut_headers,
        )
        assert response.status_code == 200
        assert rag_mock.add_documents.called

    async def test_chroma_sync_failure_returns_200(self, app_client) -> None:
        client, finding_id, rag_mock, _, mut_headers, project_id = app_client
        rag_mock.add_documents.side_effect = Exception("chroma error")
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "low"},
            headers=mut_headers,
        )
        assert response.status_code == 200

    async def test_patch_invalid_severity_returns_422(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"severity": "extreme"},
            headers=mut_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    async def test_patch_invalid_status_returns_422(self, app_client) -> None:
        client, finding_id, _, _, mut_headers, project_id = app_client
        response = await client.patch(
            f"/api/v1/projects/{project_id}/findings/{finding_id}",
            json={"status": "maybe"},
            headers=mut_headers,
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
