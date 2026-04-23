"""Unit tests for FindingAnalystService lock-aware write methods."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.findings.analyst_service import FindingAnalystService
from application.locking import FindingsBusy
from application.locking.exceptions import HolderMismatch
from application.locking.registry import LockRegistry


def _make_service(
    repo: MagicMock | None = None,
    registry: LockRegistry | None = None,
) -> FindingAnalystService:
    return FindingAnalystService(
        repo=repo or MagicMock(),
        registry=registry or LockRegistry(),
    )


class TestUpdateFields:
    def test_happy_path_acquires_and_releases_lock(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = True
        registry = LockRegistry()
        service = _make_service(repo, registry)

        result = service.update_fields(1, {"severity": "low"}, holder_token="tok")

        assert result is True
        assert not registry.is_finding_locked(1)

    def test_raises_findings_busy_when_held_by_another(self) -> None:
        repo = MagicMock()
        registry = LockRegistry()
        registry.acquire_findings([1], "other-holder")
        service = _make_service(repo, registry)

        with pytest.raises(FindingsBusy):
            service.update_fields(1, {"severity": "low"}, holder_token="my-token")

    def test_lock_released_on_write_failure(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.side_effect = RuntimeError("db error")
        registry = LockRegistry()
        service = _make_service(repo, registry)

        with pytest.raises(RuntimeError):
            service.update_fields(1, {"severity": "low"}, holder_token="tok")

        assert not registry.is_finding_locked(1)


class TestUpdateFieldsUnderHeldLock:
    def test_happy_path_writes_without_releasing_lock(self) -> None:
        repo = MagicMock()
        repo.update_analyst_fields.return_value = True
        registry = LockRegistry()
        registry.acquire_findings([1], "triage-run:1")
        service = _make_service(repo, registry)

        result = service.update_fields_under_held_lock(
            1, {"severity": "low"}, holder_token="triage-run:1"
        )

        assert result is True
        assert registry.is_finding_locked(1)

    def test_raises_holder_mismatch_on_wrong_holder(self) -> None:
        repo = MagicMock()
        registry = LockRegistry()
        registry.acquire_findings([1], "triage-run:1")
        service = _make_service(repo, registry)

        with pytest.raises(HolderMismatch):
            service.update_fields_under_held_lock(
                1, {"severity": "low"}, holder_token="wrong-holder"
            )

    def test_raises_holder_mismatch_when_not_held(self) -> None:
        repo = MagicMock()
        registry = LockRegistry()
        service = _make_service(repo, registry)

        with pytest.raises(HolderMismatch):
            service.update_fields_under_held_lock(
                1, {"severity": "low"}, holder_token="triage-run:1"
            )


class TestBulkUpdateFields:
    def test_all_unlocked_all_updated(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = {"id": 1}
        repo.update_analyst_fields.return_value = True
        registry = LockRegistry()
        service = _make_service(repo, registry)

        result = service.bulk_update_fields(
            [1, 2, 3], {"severity": "low"}, holder_token="tok"
        )

        assert sorted(result.updated) == [1, 2, 3]
        assert result.skipped_locked == []
        assert result.not_found == []
        assert result.skip_reasons == {}

    def test_locked_rows_skipped_rest_updated(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = {"id": 1}
        repo.update_analyst_fields.return_value = True
        registry = LockRegistry()
        registry.acquire_findings([2], "other-holder")
        service = _make_service(repo, registry)

        result = service.bulk_update_fields(
            [1, 2, 3], {"severity": "low"}, holder_token="my-tok"
        )

        assert sorted(result.updated) == [1, 3]
        assert result.skipped_locked == [2]
        assert result.skip_reasons == {2: "FINDING_LOCKED"}
        assert result.not_found == []

    def test_unknown_ids_in_not_found(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = None
        service = _make_service(repo)

        result = service.bulk_update_fields(
            [99], {"severity": "low"}, holder_token="tok"
        )

        assert result.not_found == [99]
        assert result.updated == []
        assert result.skipped_locked == []

    def test_empty_ids_returns_empty_result(self) -> None:
        service = _make_service()

        result = service.bulk_update_fields([], {"severity": "low"}, holder_token="tok")

        assert result.updated == []
        assert result.skipped_locked == []
        assert result.not_found == []
        assert result.skip_reasons == {}


class TestBulkUpdateFieldsUnderHeldLock:
    def test_happy_path_all_updated(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = {"id": 1}
        repo.update_analyst_fields.return_value = True
        registry = LockRegistry()
        registry.acquire_findings([1, 2], "triage-run:1")
        service = _make_service(repo, registry)

        result = service.bulk_update_fields_under_held_lock(
            [1, 2], {"severity": "low"}, holder_token="triage-run:1"
        )

        assert sorted(result.updated) == [1, 2]
        assert result.skipped_locked == []
        assert result.not_found == []

    def test_raises_holder_mismatch_on_wrong_holder(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = {"id": 1}
        registry = LockRegistry()
        registry.acquire_findings([1], "triage-run:1")
        service = _make_service(repo, registry)

        with pytest.raises(HolderMismatch):
            service.bulk_update_fields_under_held_lock(
                [1], {"severity": "low"}, holder_token="wrong-holder"
            )

    def test_not_found_ids_skipped_without_assert(self) -> None:
        repo = MagicMock()
        repo.get_finding.return_value = None
        registry = LockRegistry()
        service = _make_service(repo, registry)

        result = service.bulk_update_fields_under_held_lock(
            [99], {"severity": "low"}, holder_token="triage-run:1"
        )

        assert result.not_found == [99]
        assert result.updated == []
