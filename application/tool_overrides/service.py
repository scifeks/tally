"""Application-layer service for tool overrides.

CRUD orchestration with location-specific validation and field
normalization. Depends only on ToolOverridesRepositoryPort. No
infrastructure imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from domain.tool_overrides.entry import ToolOverride

if TYPE_CHECKING:
    from application.ports.tool_overrides import ToolOverridesRepositoryPort


_ARGS_MODES: tuple[str, ...] = ("stock", "custom")
_TYPES: tuple[str, ...] = ("repo", "api")
_LOCATIONS: tuple[str, ...] = ("local", "docker")


@dataclass(frozen=True)
class FieldError:
    """Single field validation error."""

    field: str
    issue: str


class ToolOverrideValidationError(Exception):
    """Raised when one or more validation rules fail."""

    def __init__(self, fields: list[FieldError]) -> None:
        self.fields: tuple[FieldError, ...] = tuple(fields)
        super().__init__(f"validation failed: {len(self.fields)} field error(s)")


class ToolOverrideNotFound(Exception):
    """Raised when no override exists for the given tool name."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"tool_override for tool {tool_name!r} not found")


class ToolOverridesService:
    """Application service for tool overrides."""

    def __init__(self, repo: ToolOverridesRepositoryPort) -> None:
        self._repo = repo

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[ToolOverride], int]:
        """List overrides with pagination."""
        return self._repo.list_paginated(offset=offset, limit=limit)

    def get(self, tool_name: str) -> ToolOverride | None:
        """Look up an override by tool name; None when absent."""
        return self._repo.get_by_tool_name(tool_name)

    def create(
        self,
        *,
        tool_name: str,
        args_mode: str,
        type: str,
        location: str,
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
    ) -> ToolOverride:
        """Create a new override.

        Validates all input first; raises ToolOverrideValidationError on
        any failure. Normalizes location-irrelevant fields to None.
        Propagates ToolOverrideNameConflict from the repository.
        """
        self._validate_input(
            tool_name=tool_name,
            args_mode=args_mode,
            type_=type,
            location=location,
            path=path,
            container_name=container_name,
            container_tool_path=container_tool_path,
        )
        norm_path, norm_cn, norm_ctp = _normalize(
            location, path, container_name, container_tool_path
        )
        self._repo.insert(
            tool_name=tool_name,
            args_mode=cast(Literal["stock", "custom"], args_mode),
            type=cast(Literal["repo", "api"], type),
            location=cast(Literal["local", "docker"], location),
            path=norm_path,
            container_name=norm_cn,
            container_tool_path=norm_ctp,
        )
        result = self._repo.get_by_tool_name(tool_name)
        assert result is not None
        return result

    def replace(
        self,
        tool_name: str,
        *,
        args_mode: str,
        type: str,
        location: str,
        path: str | None = None,
        container_name: str | None = None,
        container_tool_path: str | None = None,
    ) -> ToolOverride:
        """Replace an existing override.

        Validates all input first. Reads the current row to detect
        missing tool names early; raises ToolOverrideNotFound when no
        row exists. Normalizes location-irrelevant fields to None
        before delegating to the repository.
        """
        self._validate_input(
            tool_name=tool_name,
            args_mode=args_mode,
            type_=type,
            location=location,
            path=path,
            container_name=container_name,
            container_tool_path=container_tool_path,
        )

        existing = self._repo.get_by_tool_name(tool_name)
        if existing is None:
            raise ToolOverrideNotFound(tool_name)

        norm_path, norm_cn, norm_ctp = _normalize(
            location, path, container_name, container_tool_path
        )
        self._repo.update(
            tool_name,
            args_mode=cast(Literal["stock", "custom"], args_mode),
            type=cast(Literal["repo", "api"], type),
            location=cast(Literal["local", "docker"], location),
            path=norm_path,
            container_name=norm_cn,
            container_tool_path=norm_ctp,
        )
        result = self._repo.get_by_tool_name(tool_name)
        assert result is not None
        return result

    def delete(self, tool_name: str) -> None:
        """Delete an override.

        Saved scans no longer reference overrides directly, so delete
        is unconstrained. The route layer maps the missing-tool case
        to 404 by querying first.
        """
        self._repo.delete(tool_name)

    def to_commands_dict(self) -> dict[str, dict]:
        """Serialize all overrides to commands dict format."""
        rows, _total = self._repo.list_paginated(offset=0, limit=10_000)
        out: dict[str, dict] = {}
        for o in rows:
            container = None
            if o.container_name and o.container_tool_path:
                container = {
                    "name": o.container_name,
                    "tool_path": o.container_tool_path,
                }
            out[o.tool_name] = {
                "type": o.type,
                "location": o.location,
                "path": o.path or "",
                "container": container,
                "args_mode": o.args_mode,
            }
        return out

    def sync(self, desired: dict[str, dict]) -> None:
        """Reconcile current state with desired state.

        Creates, updates, and deletes overrides as needed to reach
        the desired command configuration.
        """
        current_rows, _ = self._repo.list_paginated(offset=0, limit=10_000)
        current = {r.tool_name: r for r in current_rows}
        desired_names = set(desired.keys())
        for tool_name, entry in desired.items():
            kwargs = _entry_to_service_kwargs(entry)
            if tool_name in current:
                self.replace(tool_name, **kwargs)
            else:
                self.create(tool_name=tool_name, **kwargs)
        for tool_name in current:
            if tool_name not in desired_names:
                self.delete(tool_name)

    def _validate_input(
        self,
        *,
        tool_name: str,
        args_mode: str,
        type_: str,
        location: str,
        path: str | None,
        container_name: str | None,
        container_tool_path: str | None,
    ) -> None:
        """Collect every field error in one pass before raising."""
        errors: list[FieldError] = []

        if not tool_name:
            errors.append(FieldError(field="toolName", issue="must not be empty"))
        if args_mode not in _ARGS_MODES:
            errors.append(
                FieldError(field="argsMode", issue="must be one of stock, custom")
            )
        if type_ not in _TYPES:
            errors.append(FieldError(field="type", issue="must be one of repo, api"))
        if location not in _LOCATIONS:
            errors.append(
                FieldError(field="location", issue="must be one of local, docker")
            )

        if args_mode != "custom":
            if location == "local" and not path:
                errors.append(
                    FieldError(
                        field="path",
                        issue="required when location is 'local'",
                    )
                )
            elif location == "docker":
                if not container_name:
                    errors.append(
                        FieldError(
                            field="container.name",
                            issue="required when location is 'docker'",
                        )
                    )
                if not container_tool_path:
                    errors.append(
                        FieldError(
                            field="container.toolPath",
                            issue="required when location is 'docker'",
                        )
                    )

        if errors:
            raise ToolOverrideValidationError(errors)


def _normalize(
    location: str,
    path: str | None,
    container_name: str | None,
    container_tool_path: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Clear fields not relevant to the given location.

    Returns (path, container_name, container_tool_path) with the
    irrelevant slots set to None.
    """
    if location == "local":
        return path, None, None
    return None, container_name, container_tool_path


def _entry_to_service_kwargs(entry: dict) -> dict:
    """Convert commands dict entry to service method kwargs."""
    container = entry.get("container")
    return {
        "args_mode": entry.get("args_mode", "stock"),
        "type": entry["type"],
        "location": entry["location"],
        "path": entry.get("path") or None,
        "container_name": container["name"] if container else None,
        "container_tool_path": container["tool_path"] if container else None,
    }
