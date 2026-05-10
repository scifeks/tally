"""Unit tests for SavedScansService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.ports.saved_scans import SavedScanNameConflict
from application.saved_scans.service import (
    FieldError,
    SavedScanNotFound,
    SavedScansService,
    SavedScanValidationError,
)
from domain.saved_scans.entry import (
    SavedScan,
    SavedScanArgProfileRef,
    SavedScanHydrated,
    SavedScanRepoRef,
    SavedScanToolRef,
)


def _make_repo_mock() -> MagicMock:
    return MagicMock()


def _make_profiles_repo_mock(existing: list[int] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.existing_ids.return_value = list(existing or [])
    return repo


def _make_registry_mock(names: list[str] | None = None) -> MagicMock:
    registry = MagicMock()
    registry.list_tool_names.return_value = list(names or [])
    return registry


def _make_hydrated(saved_scan_id: int, name: str = "weekly") -> SavedScanHydrated:
    return SavedScanHydrated(
        saved_scan=SavedScan(
            id=saved_scan_id,
            name=name,
            skip_enrichment=False,
            created_at="2026-05-03T12:00:00+00:00",
            updated_at="2026-05-03T12:00:00+00:00",
        ),
        repos=[
            SavedScanRepoRef(id=1, name="auth", deleted_at=None),
        ],
        tools=[SavedScanToolRef(tool_name="gitleaks")],
        skip_tool_names=[],
        segments=[],
        arg_profiles=[
            SavedScanArgProfileRef(id=12, tool_name="gitleaks", name="verbose"),
        ],
    )


class TestValidateCreate:
    def test_empty_name_raises_validation_error(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert FieldError(field="name", issue="must not be empty") in fields

    def test_at_least_one_of_tool_names_or_profile_ids_required(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[1],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert any(f.field == "toolNames" for f in fields)
        assert any("argProfileIds" in f.issue for f in fields)

    def test_unknown_tool_name_raises_with_indexed_field(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks", "trufflehog"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert any(
            f.field == "toolNames[1]" and "trufflehog" in f.issue for f in fields
        )

    def test_unknown_arg_profile_id_raises_with_indexed_field(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(existing=[12]),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[12, 99],
            )

        fields = excinfo.value.fields
        assert any(f.field == "argProfileIds[1]" and "99" in f.issue for f in fields)

    def test_multiple_errors_collected_in_one_raise(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(existing=[]),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["semgrep"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[42],
            )

        fields = excinfo.value.fields
        assert len(fields) == 3

    def test_arg_profile_existing_check_skipped_for_empty_list(self) -> None:
        profiles_repo = _make_profiles_repo_mock()
        repo = _make_repo_mock()
        repo.insert.return_value = 1
        repo.get_hydrated.return_value = _make_hydrated(1)
        service = SavedScansService(
            repo,
            profiles_repo,
            _make_registry_mock(["gitleaks"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is not None


class TestValidateReplace:
    def test_empty_name_raises_validation_error(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.replace(
                1,
                name="",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert FieldError(field="name", issue="must not be empty") in fields

    def test_at_least_one_of_tool_names_or_profile_ids_required(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(),
        )

        with pytest.raises(SavedScanValidationError):
            service.replace(
                1,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[1],
                tool_names=[],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

    def test_unknown_tool_name_raises(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError):
            service.replace(
                1,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["semgrep"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )


class TestCreateOrchestration:
    def test_insert_called_with_passed_through_args(self) -> None:
        repo = _make_repo_mock()
        repo.insert.return_value = 11
        repo.get_hydrated.return_value = _make_hydrated(11)
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(existing=[12]),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=True,
            repo_ids=[1, 2],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[12],
        )

        assert result is not None
        repo.insert.assert_called_once()

    def test_create_returns_freshly_hydrated_row(self) -> None:
        repo = _make_repo_mock()
        repo.insert.return_value = 11
        hydrated = _make_hydrated(11)
        repo.get_hydrated.return_value = hydrated
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is hydrated
        repo.get_hydrated.assert_called_once_with(11)

    def test_create_propagates_name_conflict(self) -> None:
        repo = _make_repo_mock()
        repo.insert.side_effect = SavedScanNameConflict("weekly")
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanNameConflict):
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        repo.get_hydrated.assert_not_called()


class TestReplaceOrchestration:
    def test_replace_raises_not_found_before_any_write(self) -> None:
        repo = _make_repo_mock()
        repo.get_hydrated.return_value = None
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanNotFound) as excinfo:
            service.replace(
                42,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )

        assert excinfo.value.saved_scan_id == 42

    def test_replace_calls_repo_replace_with_passed_through_args(self) -> None:
        repo = _make_repo_mock()
        repo.get_hydrated.side_effect = [
            _make_hydrated(7, name="old"),
            _make_hydrated(7, name="weekly"),
        ]
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(existing=[12]),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.replace(
            7,
            name="weekly",
            skip_enrichment=True,
            repo_ids=[1],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[12],
        )

        assert result is not None
        repo.replace.assert_called_once()

    def test_replace_returns_freshly_hydrated_row(self) -> None:
        repo = _make_repo_mock()
        first = _make_hydrated(7, name="old")
        second = _make_hydrated(7, name="weekly")
        repo.get_hydrated.side_effect = [first, second]
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.replace(
            7,
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is second

    def test_replace_propagates_name_conflict(self) -> None:
        repo = _make_repo_mock()
        repo.get_hydrated.return_value = _make_hydrated(7)
        repo.replace.side_effect = SavedScanNameConflict("weekly")
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanNameConflict):
            service.replace(
                7,
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=[],
                arg_profile_ids=[],
            )


class TestValidateSkipToolNames:
    def test_unknown_skip_tool_name_raises_indexed_error(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks", "semgrep"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=["gitleaks", "xsstrike"],
                segments=[],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert any(
            f.field == "skipToolNames[1]" and "xsstrike" in f.issue for f in fields
        )

    def test_known_skip_tool_name_passes(self) -> None:
        repo = _make_repo_mock()
        repo.insert.return_value = 1
        repo.get_hydrated.return_value = _make_hydrated(1)
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks", "semgrep"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=["semgrep"],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is not None

    def test_empty_skip_tool_names_skips_validation(self) -> None:
        repo = _make_repo_mock()
        registry = _make_registry_mock(["gitleaks"])
        repo.insert.return_value = 1
        repo.get_hydrated.return_value = _make_hydrated(1)
        service = SavedScansService(repo, _make_profiles_repo_mock(), registry)

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is not None


class TestValidateSegments:
    def test_unknown_segment_raises_indexed_error(self) -> None:
        service = SavedScansService(
            _make_repo_mock(),
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        with pytest.raises(SavedScanValidationError) as excinfo:
            service.create(
                name="weekly",
                skip_enrichment=False,
                repo_ids=[],
                tool_names=["gitleaks"],
                skip_tool_names=[],
                segments=["sast", "badvalue"],
                arg_profile_ids=[],
            )

        fields = excinfo.value.fields
        assert any(f.field == "segments[1]" and "badvalue" in f.issue for f in fields)

    def test_known_segments_pass(self) -> None:
        repo = _make_repo_mock()
        repo.insert.return_value = 1
        repo.get_hydrated.return_value = _make_hydrated(1)
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=["sast", "secrets"],
            arg_profile_ids=[],
        )

        assert result is not None

    def test_empty_segments_skips_validation(self) -> None:
        repo = _make_repo_mock()
        repo.insert.return_value = 1
        repo.get_hydrated.return_value = _make_hydrated(1)
        service = SavedScansService(
            repo,
            _make_profiles_repo_mock(),
            _make_registry_mock(["gitleaks"]),
        )

        result = service.create(
            name="weekly",
            skip_enrichment=False,
            repo_ids=[],
            tool_names=["gitleaks"],
            skip_tool_names=[],
            segments=[],
            arg_profile_ids=[],
        )

        assert result is not None
