"""Unit tests for ToolArgProfilesService."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from application.tool_arg_profiles.service import (
    FileArgInput,
    FlagArgInput,
    StringArgInput,
    ToolArgProfileNotFound,
    ToolArgProfilesService,
    ToolArgProfileValidationError,
)
from domain.tool_arg_profiles.entry import (
    ToolArgProfile,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
)


def _make_profile(
    profile_id: int = 1,
    tool_name: str = "semgrep",
    name: str = "test_profile",
    args: list | None = None,
) -> ToolArgProfile:
    """Helper to build a domain ToolArgProfile for mocking."""
    if args is None:
        args = []
    return ToolArgProfile(
        id=profile_id,
        tool_name=tool_name,
        name=name,
        args=args,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


def _make_repo_mock() -> MagicMock:
    """Create a mock repository port."""
    return MagicMock()


def _make_storage_mock() -> MagicMock:
    """Create a mock storage port."""
    return MagicMock()


class TestValidateCreate:
    """Validation rules for create operation."""

    def test_empty_tool_name_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(tool_name="", name="test", args=[])

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "toolName"
        assert exc_info.value.fields[0].issue == "must not be empty"

    def test_empty_name_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(tool_name="semgrep", name="", args=[])

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "name"
        assert exc_info.value.fields[0].issue == "must not be empty"

    def test_empty_arg_name_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[FlagArgInput(name="")],
            )

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "args[0].name"
        assert exc_info.value.fields[0].issue == "must not be empty"

    def test_duplicate_arg_names_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[
                    FlagArgInput(name="debug"),
                    StringArgInput(name="output", value="file.json"),
                    FlagArgInput(name="debug"),
                ],
            )

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "args[2].name"
        assert "duplicate name 'debug'" in exc_info.value.fields[0].issue

    def test_file_arg_with_none_data_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=None)],
            )

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "args[0].data"
        assert exc_info.value.fields[0].issue == "must not be empty on create"

    def test_multiple_validation_errors_collected(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.create(
                tool_name="",
                name="",
                args=[
                    FlagArgInput(name=""),
                    FileArgInput(name="rules", data=None),
                ],
            )

        assert len(exc_info.value.fields) == 4
        field_names = [f.field for f in exc_info.value.fields]
        assert "toolName" in field_names
        assert "name" in field_names
        assert "args[0].name" in field_names
        assert "args[1].data" in field_names


class TestCreateOrchestration:
    """Verify create operation calls and sequencing."""

    def test_repo_insert_called_with_placeholder_file_args(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        repo.get.return_value = _make_profile()
        svc = ToolArgProfilesService(repo, storage)

        svc.create(
            tool_name="semgrep",
            name="test",
            args=[
                FlagArgInput(name="debug"),
                FileArgInput(name="rules", data=b"rule: test"),
            ],
        )

        repo.insert.assert_called_once()
        call_args = repo.insert.call_args
        args_list = call_args[1]["args"]
        assert len(args_list) == 2
        assert isinstance(args_list[0], ToolArgProfileFlagArg)
        assert isinstance(args_list[1], ToolArgProfileFileArg)
        assert args_list[1].path == ""

    def test_storage_write_called_for_file_args(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.return_value = "/path/to/rules"
        repo.get.return_value = _make_profile(
            args=[
                ToolArgProfileFlagArg(name="debug"),
                ToolArgProfileFileArg(name="rules", path="/path/to/rules"),
            ]
        )
        svc = ToolArgProfilesService(repo, storage)

        data = b"rule: test"
        svc.create(
            tool_name="semgrep",
            name="test",
            args=[
                FlagArgInput(name="debug"),
                FileArgInput(name="rules", data=data),
            ],
        )

        storage.write.assert_called_once_with(1, "rules", data, original_filename=None)

    def test_repo_update_called_with_paths_from_storage(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.return_value = "/path/to/rules"
        repo.get.return_value = _make_profile(
            args=[ToolArgProfileFileArg(name="rules", path="/path/to/rules")]
        )
        svc = ToolArgProfilesService(repo, storage)

        svc.create(
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=b"rule: test")],
        )

        repo.update.assert_called_once()
        call_args = repo.update.call_args
        args_list = call_args[1]["args"]
        assert len(args_list) == 1
        assert isinstance(args_list[0], ToolArgProfileFileArg)
        assert args_list[0].path == "/path/to/rules"

    def test_result_returned_from_repo_get(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.return_value = "/path"
        expected = _make_profile()
        repo.get.return_value = expected
        svc = ToolArgProfilesService(repo, storage)

        result = svc.create(
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=b"x")],
        )

        assert result == expected


class TestCreateRollback:
    """Rollback when storage or repo update fails."""

    def test_rollback_on_storage_write_failure(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.side_effect = RuntimeError("write failed")
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="write failed"):
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=b"x")],
            )

        repo.delete.assert_called_once_with(1)
        storage.delete_profile_dir.assert_called_once_with(1)

    def test_rollback_on_second_file_arg_failure(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.side_effect = [
            "/path/to/first",
            RuntimeError("second write failed"),
        ]
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="second write failed"):
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[
                    FileArgInput(name="first", data=b"x"),
                    FileArgInput(name="second", data=b"y"),
                ],
            )

        storage.delete.assert_called_once_with(1, "first")
        repo.delete.assert_called_once_with(1)
        storage.delete_profile_dir.assert_called_once_with(1)

    def test_rollback_on_repo_update_failure(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.insert.return_value = 1
        storage.write.return_value = "/path"
        repo.update.side_effect = RuntimeError("update failed")
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="update failed"):
            svc.create(
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=b"x")],
            )

        storage.delete.assert_called_once_with(1, "rules")
        repo.delete.assert_called_once_with(1)
        storage.delete_profile_dir.assert_called_once_with(1)


class TestValidateReplace:
    """Validation rules for replace operation."""

    def test_empty_tool_name_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.replace(1, tool_name="", name="test", args=[])

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "toolName"
        assert exc_info.value.fields[0].issue == "must not be empty"

    def test_empty_name_raises_validation_error(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.replace(1, tool_name="semgrep", name="", args=[])

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "name"
        assert exc_info.value.fields[0].issue == "must not be empty"

    def test_keep_existing_reference_nonexistent_arg(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(args=[ToolArgProfileFlagArg(name="debug")])
        repo.get.return_value = existing
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.replace(
                1,
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=None)],
            )

        assert len(exc_info.value.fields) == 1
        assert exc_info.value.fields[0].field == "args[0].data"
        assert "keep-existing referenced but no current file" in (
            exc_info.value.fields[0].issue
        )

    def test_keep_existing_reference_missing_stored_bytes(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[ToolArgProfileFileArg(name="rules", path="/path")]
        )
        repo.get.return_value = existing
        storage.read.return_value = None
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileValidationError) as exc_info:
            svc.replace(
                1,
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=None)],
            )

        assert len(exc_info.value.fields) == 1
        assert "keep-existing referenced but stored bytes are missing" in (
            exc_info.value.fields[0].issue
        )

    def test_nonexistent_profile_raises_not_found(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.get.return_value = None
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(ToolArgProfileNotFound) as exc_info:
            svc.replace(
                999,
                tool_name="semgrep",
                name="test",
                args=[],
            )

        assert exc_info.value.profile_id == 999


class TestReplaceOrchestration:
    """Verify replace operation calls and sequencing."""

    def test_snapshot_taken_for_overwrite(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[ToolArgProfileFileArg(name="rules", path="/old/path")]
        )
        repo.get.return_value = existing
        storage.read.return_value = b"old rules data"
        storage.write.return_value = "/new/path"
        repo.get.side_effect = [existing, existing]
        svc = ToolArgProfilesService(repo, storage)

        svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=b"new rules data")],
        )

        storage.read.assert_called_once_with(1, "rules")
        assert storage.write.call_count == 1

    def test_write_called_for_new_bytes(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(args=[ToolArgProfileFlagArg(name="debug")])
        repo.get.return_value = existing
        storage.write.return_value = "/path/to/rules"
        svc = ToolArgProfilesService(repo, storage)

        svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=b"new rules")],
        )

        storage.write.assert_called_once_with(
            1, "rules", b"new rules", original_filename=None
        )

    def test_no_write_for_keep_existing(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[ToolArgProfileFileArg(name="rules", path="/old/path")]
        )
        repo.get.return_value = existing
        storage.read.return_value = b"old data"
        svc = ToolArgProfilesService(repo, storage)

        svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=None)],
        )

        storage.write.assert_not_called()

    def test_orphan_files_deleted_post_commit(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[
                ToolArgProfileFileArg(name="rules", path="/old/path"),
                ToolArgProfileFileArg(name="config", path="/old/config"),
            ]
        )
        repo.get.return_value = existing
        storage.read.return_value = b"old data"
        svc = ToolArgProfilesService(repo, storage)

        svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[FileArgInput(name="rules", data=None)],
        )

        storage.delete.assert_called_once_with(1, "config")

    def test_update_called_with_correct_paths(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[
                ToolArgProfileFlagArg(name="debug"),
                ToolArgProfileFileArg(name="rules", path="/old/path"),
            ]
        )
        repo.get.return_value = existing
        storage.read.return_value = b"old data"
        svc = ToolArgProfilesService(repo, storage)

        svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[
                FlagArgInput(name="debug"),
                FileArgInput(name="rules", data=None),
            ],
        )

        repo.update.assert_called_once()
        call_args = repo.update.call_args
        args_list = call_args[1]["args"]
        file_arg = next(
            (a for a in args_list if isinstance(a, ToolArgProfileFileArg)),
            None,
        )
        assert file_arg is not None
        assert file_arg.path == "/old/path"

    def test_result_returned_from_repo_get(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        expected = _make_profile()
        repo.get.return_value = expected
        svc = ToolArgProfilesService(repo, storage)

        result = svc.replace(
            1,
            tool_name="semgrep",
            name="test",
            args=[FlagArgInput(name="debug")],
        )

        assert result == expected


class TestReplaceRollback:
    """Rollback when repo update fails in replace."""

    def test_rollback_restores_snapshotted_bytes(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(
            args=[ToolArgProfileFileArg(name="rules", path="/old/path")]
        )
        repo.get.return_value = existing
        storage.read.return_value = b"old data"
        repo.update.side_effect = RuntimeError("update failed")
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="update failed"):
            svc.replace(
                1,
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=b"new data")],
            )

        storage.write.assert_any_call(1, "rules", b"old data")

    def test_rollback_deletes_new_files(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        existing = _make_profile(args=[ToolArgProfileFlagArg(name="debug")])
        repo.get.return_value = existing
        storage.write.return_value = "/path/to/rules"
        repo.update.side_effect = RuntimeError("update failed")
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="update failed"):
            svc.replace(
                1,
                tool_name="semgrep",
                name="test",
                args=[FileArgInput(name="rules", data=b"new data")],
            )

        storage.delete.assert_called_once_with(1, "rules")


class TestDelete:
    """Verify delete operation."""

    def test_repo_delete_called_before_storage_delete(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        call_order = []

        def repo_delete_side_effect(profile_id: int) -> None:
            call_order.append("repo_delete")

        def storage_delete_side_effect(profile_id: int) -> None:
            call_order.append("storage_delete")

        repo.delete.side_effect = repo_delete_side_effect
        storage.delete_profile_dir.side_effect = storage_delete_side_effect
        svc = ToolArgProfilesService(repo, storage)

        svc.delete(1)

        assert call_order == ["repo_delete", "storage_delete"]

    def test_repo_integrity_error_propagates_without_storage_delete(
        self,
    ) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        repo.delete.side_effect = RuntimeError("foreign key constraint")
        svc = ToolArgProfilesService(repo, storage)

        with pytest.raises(RuntimeError, match="foreign key constraint"):
            svc.delete(1)

        storage.delete_profile_dir.assert_not_called()


class TestThinPassThroughs:
    """Verify simple delegation methods."""

    def test_list_delegates_to_repo(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        expected_profiles = [_make_profile(), _make_profile(profile_id=2)]
        expected_total = 2
        repo.list_paginated.return_value = (expected_profiles, expected_total)
        svc = ToolArgProfilesService(repo, storage)

        profiles, total = svc.list(tool_name="semgrep", offset=10, limit=20)

        repo.list_paginated.assert_called_once_with(
            tool_name="semgrep", offset=10, limit=20
        )
        assert profiles == expected_profiles
        assert total == expected_total

    def test_get_delegates_to_repo(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        expected = _make_profile()
        repo.get.return_value = expected
        svc = ToolArgProfilesService(repo, storage)

        result = svc.get(1)

        repo.get.assert_called_once_with(1)
        assert result == expected

    def test_read_file_arg_delegates_to_storage(self) -> None:
        repo = _make_repo_mock()
        storage = _make_storage_mock()
        expected_data = b"file contents"
        storage.read.return_value = expected_data
        svc = ToolArgProfilesService(repo, storage)

        result = svc.read_file_arg(1, "rules")

        storage.read.assert_called_once_with(1, "rules")
        assert result == expected_data
