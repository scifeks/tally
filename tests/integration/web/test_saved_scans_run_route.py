"""Integration tests for the saved-scan run route."""

from __future__ import annotations

from typing import Any

import pytest

from infrastructure.store.repositories.repositories import RepositoryRepository
from infrastructure.store.repositories.saved_scans import SavedScansRepository
from infrastructure.store.repositories.tool_arg_profiles import (
    ToolArgProfilesRepository,
)

pytestmark = pytest.mark.integration


def _seed_repo(factory, name: str) -> int:
    """Insert a row into ``repositories`` and return its id."""
    with factory.connect() as conn:
        cur = conn.execute(
            "INSERT INTO repositories (name) VALUES (?)",
            (name,),
        )
        return int(cur.lastrowid)


def _read_run_row(factory, run_id: int) -> dict[str, Any]:
    """Fetch a row from scan_runs as a dict for assertion."""
    with factory.connect() as conn:
        row = conn.execute(
            "SELECT * FROM scan_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
    assert row is not None, f"scan_runs row {run_id} missing"
    return dict(row)


class TestSavedScansRun:
    """Tests for POST /api/v1/projects/{project_id}/saved-scans/{id}/run."""

    async def test_run_dispatches_and_returns_202(
        self, app_client, monkeypatch
    ) -> None:
        """Happy path returns 202 and writes saved_scan_id on the new run."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        repo_id = _seed_repo(factory, "auth-service")
        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert isinstance(body["id"], int)
        assert body["status"] == "queued"
        assert body["project_id"] == project_id

        run_row = _read_run_row(factory, body["id"])
        assert run_row["saved_scan_id"] == scan_id

        assert len(spawned) == 1
        assert spawned[0]["repo_ids"] == ("auth-service",)
        assert spawned[0]["tool_ids"] == ("gitleaks",)

    async def test_run_passes_arg_profile_ids_to_dispatch(
        self, app_client, monkeypatch
    ) -> None:
        """Arg-profile ids on the saved scan flow into start_scan kwargs."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        spawned: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: spawned.append(kw),
        )

        profiles_repo = ToolArgProfilesRepository(factory)
        profile_id = profiles_repo.insert(
            tool_name="gitleaks",
            name="verbose",
            args=[],
        )
        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="with-profile",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[profile_id],
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert resp.status_code == 202, resp.text

        run_id = resp.json()["id"]
        run_row = _read_run_row(factory, run_id)
        assert run_row["saved_scan_id"] == scan_id

        with factory.connect() as conn:
            snap_row = conn.execute(
                "SELECT arg_profile_snapshot FROM run_tools "
                "WHERE run_id = ? AND tool = ?",
                (run_id, "gitleaks"),
            ).fetchone()
        assert snap_row is not None
        assert snap_row["arg_profile_snapshot"] == "[]"

    async def test_run_409_stale_repo(self, app_client, monkeypatch) -> None:
        """Soft-deleted repo on a saved scan returns 409 STALE_SAVED_SCAN."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        repo_id = _seed_repo(factory, "going-away")
        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="stale-repo",
            skip_enrichment=False,
            repo_ids=[repo_id],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )
        RepositoryRepository(factory).soft_delete(repo_id)

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"]["code"] == "STALE_SAVED_SCAN"
        items = body["error"]["details"]["staleItems"]
        assert items == [
            {"kind": "repo", "id": repo_id, "name": "going-away"},
        ]

    async def test_run_409_stale_tool(self, app_client, monkeypatch) -> None:
        """Saved scan referencing an unregistered tool returns 409 STALE."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        # Bypass service validation by inserting through the repo directly:
        # the repo is unconstrained on tool names, so a name absent from the
        # local-wrappers fallback registry will register as STALE at run time.
        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="stale-tool",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["definitely-not-a-tool"],
            arg_profile_ids=[],
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"]["code"] == "STALE_SAVED_SCAN"
        items = body["error"]["details"]["staleItems"]
        assert items == [{"kind": "tool", "name": "definitely-not-a-tool"}]

    async def test_run_409_stale_arg_profile(self, app_client, monkeypatch) -> None:
        """Orphan arg-profile join row returns 409 STALE_SAVED_SCAN."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="stale-profile",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        # Seed an orphan join row pointing at a non-existent profile id.
        with factory.connect() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute(
                "INSERT INTO saved_scan_arg_profiles "
                "(saved_scan_id, arg_profile_id) VALUES (?, ?)",
                (scan_id, 9999),
            )
            conn.execute("PRAGMA foreign_keys = ON")

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["error"]["code"] == "STALE_SAVED_SCAN"
        items = body["error"]["details"]["staleItems"]
        assert items == [{"kind": "argProfile", "id": 9999}]

    async def test_run_409_when_scan_already_running(
        self, app_client, monkeypatch
    ) -> None:
        """Second run while a scan is in flight returns 409 JOB_ALREADY_RUNNING."""
        client, _fid, _kb, factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="busy",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        first = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert first.status_code == 202, first.text

        second = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
            headers=mut_headers,
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "JOB_ALREADY_RUNNING"

    async def test_run_404_unknown_saved_scan(self, app_client, monkeypatch) -> None:
        """Unknown saved scan id returns 404."""
        client, _fid, _kb, _factory, mut_headers, project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/999999/run",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_run_404_unknown_project(self, app_client, monkeypatch) -> None:
        """Unknown project id returns 404."""
        client, _fid, _kb, _factory, mut_headers, _project_id = app_client
        monkeypatch.setattr(
            "application.tools.scan_service.ScanService._run_worker",
            lambda self, **kw: None,
        )

        resp = await client.post(
            "/api/v1/projects/999999/saved-scans/1/run",
            headers=mut_headers,
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    async def test_run_403_without_csrf(self, app_client) -> None:
        """POST without CSRF token returns 403."""
        client, _fid, _kb, factory, _mut_headers, project_id = app_client
        saved = SavedScansRepository(factory)
        scan_id = saved.insert(
            name="no-csrf",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            arg_profile_ids=[],
        )

        resp = await client.post(
            f"/api/v1/projects/{project_id}/saved-scans/{scan_id}/run",
        )
        assert resp.status_code == 403
