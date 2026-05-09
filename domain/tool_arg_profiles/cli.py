"""Convert tool arg profiles to CLI argument lists."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from domain.tool_arg_profiles.entry import (
    ToolArgProfileArg,
    ToolArgProfileFileArg,
    ToolArgProfileFlagArg,
    ToolArgProfileStringArg,
)


def profile_args_to_cli(args: Sequence[ToolArgProfileArg]) -> list[str]:
    """Convert domain arg types to CLI strings."""
    result: list[str] = []
    for arg in args:
        if isinstance(arg, ToolArgProfileFlagArg):
            result.append(arg.name)
        elif isinstance(arg, ToolArgProfileStringArg):
            result.extend([arg.name, arg.value])
        elif isinstance(arg, ToolArgProfileFileArg):
            result.extend([arg.name, arg.path])
    return result


def snapshot_to_cli(snapshot_json: str) -> list[str]:
    """Parse JSON snapshot and convert to CLI argument list."""
    try:
        data = json.loads(snapshot_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e

    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data).__name__}")

    args: list[ToolArgProfileArg] = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(f"Expected dict in array, got {type(item).__name__}")

        arg_type: Any = item.get("type")
        if arg_type is None:
            raise ValueError("Missing required field: type")

        if arg_type == "flag":
            if "name" not in item:
                raise ValueError("Missing required field: name")
            args.append(ToolArgProfileFlagArg(name=item["name"]))

        elif arg_type == "string":
            if "name" not in item:
                raise ValueError("Missing required field: name")
            if "value" not in item:
                raise ValueError("Missing required field: value")
            args.append(ToolArgProfileStringArg(name=item["name"], value=item["value"]))

        elif arg_type == "file":
            if "name" not in item:
                raise ValueError("Missing required field: name")
            if "path" not in item:
                raise ValueError("Missing required field: path")
            args.append(
                ToolArgProfileFileArg(
                    name=item["name"],
                    path=item["path"],
                    original_filename=item.get("original_filename"),
                )
            )

        else:
            raise ValueError(f"Unknown arg type: {arg_type}")

    return profile_args_to_cli(args)
