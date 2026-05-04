"""Application-layer service for tool argument profiles.

Orchestrates creation, modification, and deletion of tool argument profiles
with strict atomic semantics for file storage. Validates all input before
any I/O operations; collects all validation errors and raises together.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from domain.tool_arg_profiles.entry import (
    ToolArgProfile,
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)

if TYPE_CHECKING:
    from application.ports.arg_files_storage import ArgFilesStoragePort
    from application.ports.tool_arg_profiles import (
        ToolArgProfilesRepositoryPort,
    )


@dataclass(frozen=True)
class FlagArgInput:
    """Input representation of a flag argument (no value)."""

    name: str
    type: Literal["flag"] = "flag"


@dataclass(frozen=True)
class StringArgInput:
    """Input representation of a string argument."""

    name: str
    value: str
    type: Literal["string"] = "string"


@dataclass(frozen=True)
class FileArgInput:
    """Input representation of a file argument.

    data: bytes to store or None to keep existing (replace operation only).
    """

    name: str
    data: bytes | None
    type: Literal["file"] = "file"


type ProfileArgInput = FlagArgInput | StringArgInput | FileArgInput


@dataclass(frozen=True)
class FieldError:
    """Single field validation error."""

    field: str
    issue: str


class ToolArgProfileValidationError(Exception):
    """Raised when one or more validation errors occur."""

    def __init__(self, fields: list[FieldError]) -> None:
        self.fields: tuple[FieldError, ...] = tuple(fields)
        super().__init__(f"validation failed: {len(self.fields)} field error(s)")


class ToolArgProfileNotFound(Exception):
    """Raised when a profile ID does not exist."""

    def __init__(self, profile_id: int) -> None:
        self.profile_id = profile_id
        super().__init__(f"tool_arg_profile id={profile_id} not found")


class ToolArgProfilesService:
    """Application service for tool argument profiles."""

    def __init__(
        self,
        repo: ToolArgProfilesRepositoryPort,
        storage: ArgFilesStoragePort,
    ) -> None:
        self._repo = repo
        self._storage = storage

    def list(
        self,
        *,
        tool_name: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolArgProfile], int]:
        """List profiles with optional filtering and pagination."""
        return self._repo.list_paginated(
            tool_name=tool_name, offset=offset, limit=limit
        )

    def get(self, profile_id: int) -> ToolArgProfile | None:
        """Retrieve a profile by ID, or None if not found."""
        return self._repo.get(profile_id)

    def read_file_arg(self, profile_id: int, arg_name: str) -> bytes | None:
        """Read the bytes of a file argument."""
        return self._storage.read(profile_id, arg_name)

    def create(
        self,
        *,
        tool_name: str,
        name: str,
        args: list[ProfileArgInput],
    ) -> ToolArgProfile:
        """Create a new profile.

        Validates all input before any I/O. On error, raises a
        ToolArgProfileValidationError collecting all field errors.
        On repo conflict, ToolArgProfileNameConflict propagates.
        On storage/update failure, rolls back atomically.
        """
        self._validate_create(tool_name, name, args)

        placeholder_args: list[ToolArgProfileArg] = []
        for arg in args:
            if isinstance(arg, FlagArgInput):
                placeholder_args.append(ToolArgProfileFlagArg(name=arg.name))
            elif isinstance(arg, StringArgInput):
                placeholder_args.append(
                    ToolArgProfileStringArg(name=arg.name, value=arg.value)
                )
            else:  # FileArgInput
                placeholder_args.append(ToolArgProfileFileArg(name=arg.name, path=""))

        profile_id = self._repo.insert(
            tool_name=tool_name, name=name, args=placeholder_args
        )

        written_names: list[str] = []
        paths_by_name: dict[str, str] = {}

        try:
            for arg in args:
                if isinstance(arg, FileArgInput):
                    assert arg.data is not None
                    path = self._storage.write(profile_id, arg.name, arg.data)
                    written_names.append(arg.name)
                    paths_by_name[arg.name] = path

            domain_args = self._build_domain_args(args, paths_by_name)
            self._repo.update(
                profile_id, tool_name=tool_name, name=name, args=domain_args
            )
        except Exception:
            for name_to_delete in written_names:
                with suppress(Exception):
                    self._storage.delete(profile_id, name_to_delete)
            with suppress(Exception):
                self._storage.delete_profile_dir(profile_id)
            with suppress(Exception):
                self._repo.delete(profile_id)
            raise

        result = self._repo.get(profile_id)
        assert result is not None
        return result

    def replace(
        self,
        profile_id: int,
        *,
        tool_name: str,
        name: str,
        args: list[ProfileArgInput],
    ) -> ToolArgProfile:
        """Replace a profile's args and metadata.

        Validates all input before I/O. On validation/existence errors,
        raises before any state change. On update failure, rolls back
        with snapshot restore for modified files and deletion for new
        files. Post-commit, orphaned files are cleaned up non-atomically.
        """
        self._validate_replace_args(tool_name, name, args)

        existing = self._repo.get(profile_id)
        if existing is None:
            raise ToolArgProfileNotFound(profile_id)

        old_file_args: dict[str, ToolArgProfileFileArg] = {}
        for arg in existing.args:
            if isinstance(arg, ToolArgProfileFileArg):
                old_file_args[arg.name] = arg

        self._validate_keep_existing(profile_id, args, old_file_args)

        snapshots: dict[str, bytes] = {}
        for arg in args:
            if isinstance(arg, FileArgInput) and arg.data is not None:
                if arg.name in old_file_args:
                    bytes_data = self._storage.read(profile_id, arg.name)
                    if bytes_data is not None:
                        snapshots[arg.name] = bytes_data

        written_names: list[str] = []
        paths_by_name: dict[str, str] = {}

        try:
            for arg in args:
                if isinstance(arg, FileArgInput):
                    if arg.data is None:
                        paths_by_name[arg.name] = old_file_args[arg.name].path
                    else:
                        path = self._storage.write(profile_id, arg.name, arg.data)
                        written_names.append(arg.name)
                        paths_by_name[arg.name] = path

            domain_args = self._build_domain_args(args, paths_by_name)
            self._repo.update(
                profile_id, tool_name=tool_name, name=name, args=domain_args
            )
        except Exception:
            for name_to_restore in written_names:
                with suppress(Exception):
                    if name_to_restore in snapshots:
                        self._storage.write(
                            profile_id,
                            name_to_restore,
                            snapshots[name_to_restore],
                        )
                    else:
                        self._storage.delete(profile_id, name_to_restore)
            raise

        new_file_names = {arg.name for arg in args if isinstance(arg, FileArgInput)}
        for old_name in old_file_args:
            if old_name not in new_file_names:
                self._storage.delete(profile_id, old_name)

        result = self._repo.get(profile_id)
        assert result is not None
        return result

    def delete(self, profile_id: int) -> None:
        """Delete a profile and its associated files.

        The repository delete is called first. Any IntegrityError propagates
        without attempting file deletion.
        """
        self._repo.delete(profile_id)
        self._storage.delete_profile_dir(profile_id)

    def _build_domain_args(
        self,
        args: list[ProfileArgInput],
        paths_by_name: dict[str, str],
    ) -> list[ToolArgProfileArg]:
        """Build domain arg objects from input args and resolved paths."""
        domain_args: list[ToolArgProfileArg] = []
        for arg in args:
            if isinstance(arg, FlagArgInput):
                domain_args.append(ToolArgProfileFlagArg(name=arg.name))
            elif isinstance(arg, StringArgInput):
                domain_args.append(
                    ToolArgProfileStringArg(name=arg.name, value=arg.value)
                )
            else:  # FileArgInput
                domain_args.append(
                    ToolArgProfileFileArg(name=arg.name, path=paths_by_name[arg.name])
                )
        return domain_args

    def _validate_create(
        self, tool_name: str, name: str, args: list[ProfileArgInput]
    ) -> None:
        """Validate create inputs. Raises ToolArgProfileValidationError."""
        errors: list[FieldError] = []

        if not tool_name:
            errors.append(FieldError(field="toolName", issue="must not be empty"))
        if not name:
            errors.append(FieldError(field="name", issue="must not be empty"))

        self._validate_arg_names(args, errors)

        for i, arg in enumerate(args):
            if isinstance(arg, FileArgInput) and arg.data is None:
                errors.append(
                    FieldError(
                        field=f"args[{i}].data",
                        issue="must not be empty on create",
                    )
                )

        if errors:
            raise ToolArgProfileValidationError(errors)

    def _validate_replace_args(
        self,
        tool_name: str,
        name: str,
        args: list[ProfileArgInput],
    ) -> None:
        """Validate replace inputs for tool_name, name, and args.

        Raises ToolArgProfileValidationError if issues found.
        """
        errors: list[FieldError] = []

        if not tool_name:
            errors.append(FieldError(field="toolName", issue="must not be empty"))
        if not name:
            errors.append(FieldError(field="name", issue="must not be empty"))

        self._validate_arg_names(args, errors)

        if errors:
            raise ToolArgProfileValidationError(errors)

    def _validate_arg_names(
        self,
        args: list[ProfileArgInput],
        errors: list[FieldError],
    ) -> None:
        """Append FieldError(s) for empty or duplicate arg names."""
        seen: set[str] = set()
        for i, arg in enumerate(args):
            if not arg.name:
                errors.append(
                    FieldError(field=f"args[{i}].name", issue="must not be empty")
                )
            elif arg.name in seen:
                errors.append(
                    FieldError(
                        field=f"args[{i}].name",
                        issue=f"duplicate name {arg.name!r}",
                    )
                )
            else:
                seen.add(arg.name)

    def _validate_keep_existing(
        self,
        profile_id: int,
        args: list[ProfileArgInput],
        old_file_args: dict,
    ) -> None:
        """Validate keep-existing references.

        Existence check first, then storage check. Raises
        ToolArgProfileValidationError if any fail.
        """
        errors: list[FieldError] = []

        for i, arg in enumerate(args):
            if isinstance(arg, FileArgInput) and arg.data is None:
                if arg.name not in old_file_args:
                    errors.append(
                        FieldError(
                            field=f"args[{i}].data",
                            issue="keep-existing referenced but no current file",
                        )
                    )
                else:
                    bytes_data = self._storage.read(profile_id, arg.name)
                    if bytes_data is None:
                        msg = "keep-existing referenced but stored bytes are missing"
                        errors.append(FieldError(field=f"args[{i}].data", issue=msg))

        if errors:
            raise ToolArgProfileValidationError(errors)
