"""Unit tests for FindingsService manual finding methods."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from application.findings.findings_service import FindingsService
from domain.findings.entry import Finding


def _build_service(
    *,
    finding_repo: Any = None,
    history_repo: Any = None,
    project_repo: Any = None,
    event_sink: Any = None,
) -> FindingsService:
    return FindingsService(
        finding_repo=finding_repo or MagicMock(),
        history_repo=history_repo or MagicMock(),
        project_repo=project_repo or MagicMock(),
        analyst=MagicMock(),
        lock_query=MagicMock(),
        project_id=1,
        project_name="test-project",
        findings_db_exists=True,
        event_sink=event_sink,
    )


class TestCreateManualFinding:
    def test_returns_finding(self) -> None:
        repo = MagicMock()
        repo.insert_manual_finding.return_value = 42
        repo.get_finding.return_value = Finding(
            id=42,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        svc = _build_service(finding_repo=repo)

        result = svc.create_manual_finding(
            {
                "title": "Test vuln",
                "severity": "high",
                "segment": "sast",
                "file": "src/app.py",
            }
        )
        assert result.id == 42
        assert result.tool == "manual"

    def test_sets_tool_to_manual(self) -> None:
        repo = MagicMock()
        repo.insert_manual_finding.return_value = 1
        repo.get_finding.return_value = Finding(
            id=1,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        svc = _build_service(finding_repo=repo)

        svc.create_manual_finding(
            {
                "title": "T",
                "severity": "high",
                "segment": "sast",
                "file": "f.py",
            }
        )
        call_args = repo.insert_manual_finding.call_args
        columns = call_args[0][0]
        assert columns["tool"] == "manual"

    def test_derives_domain_from_segment(self) -> None:
        repo = MagicMock()
        repo.insert_manual_finding.return_value = 1
        repo.get_finding.return_value = Finding(
            id=1,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="web",
            segment="web",
        )
        svc = _build_service(finding_repo=repo)

        svc.create_manual_finding(
            {
                "title": "T",
                "severity": "high",
                "segment": "web",
                "url": "https://example.com",
            }
        )
        call_args = repo.insert_manual_finding.call_args
        columns = call_args[0][0]
        assert columns["domain"] == "web"

    def test_missing_title_raises(self) -> None:
        svc = _build_service()
        with pytest.raises(ValueError, match="title"):
            svc.create_manual_finding(
                {"severity": "high", "segment": "sast", "file": "f"}
            )

    def test_missing_severity_raises(self) -> None:
        svc = _build_service()
        with pytest.raises(ValueError, match="severity"):
            svc.create_manual_finding({"title": "T", "segment": "sast", "file": "f"})

    def test_missing_location_raises(self) -> None:
        svc = _build_service()
        with pytest.raises(ValueError, match="location"):
            svc.create_manual_finding(
                {"title": "T", "severity": "high", "segment": "sast"}
            )

    def test_emits_created_event(self) -> None:
        repo = MagicMock()
        repo.insert_manual_finding.return_value = 1
        repo.get_finding.return_value = Finding(
            id=1,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        sink = MagicMock()
        svc = _build_service(finding_repo=repo, event_sink=sink)

        svc.create_manual_finding(
            {
                "title": "T",
                "severity": "high",
                "segment": "sast",
                "file": "f.py",
            }
        )
        sink.emit.assert_called_once()


class TestDeleteManualFinding:
    def test_deletes_manual_finding(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = Finding(
            id=10,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        lock = MagicMock()
        lock.is_finding_locked.return_value = False
        svc = _build_service(finding_repo=repo)
        svc._lock_query = lock

        svc.delete_manual_finding(10)
        repo.delete_finding_by_id.assert_called_once_with(10)

    def test_rejects_non_manual_finding(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = Finding(
            id=10,
            fingerprint="fp",
            run_id=1,
            tool="semgrep",
            domain="code",
            segment="sast",
        )
        lock = MagicMock()
        lock.is_finding_locked.return_value = False
        svc = _build_service(finding_repo=repo)
        svc._lock_query = lock

        with pytest.raises(PermissionError, match="manual"):
            svc.delete_manual_finding(10)

    def test_rejects_locked_finding(self) -> None:
        from application.locking import FindingsBusy

        repo = MagicMock()
        repo.get_finding.return_value = Finding(
            id=10,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        lock = MagicMock()
        lock.is_finding_locked.return_value = True
        lock.finding_lock_holder.return_value = "triage-job"
        svc = _build_service(finding_repo=repo)
        svc._lock_query = lock

        with pytest.raises(FindingsBusy):
            svc.delete_manual_finding(10)

    def test_not_found_raises(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = None
        svc = _build_service(finding_repo=repo)

        with pytest.raises(LookupError):
            svc.delete_manual_finding(999)

    def test_emits_deleted_event(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = Finding(
            id=10,
            fingerprint="fp",
            run_id=None,
            tool="manual",
            domain="code",
            segment="sast",
        )
        lock = MagicMock()
        lock.is_finding_locked.return_value = False
        sink = MagicMock()
        svc = _build_service(finding_repo=repo, event_sink=sink)
        svc._lock_query = lock

        svc.delete_manual_finding(10)
        sink.emit.assert_called_once()
