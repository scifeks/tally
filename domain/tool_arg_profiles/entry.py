"""Domain entries for tool argument profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ToolArgProfileFlagArg:
    name: str
    type: Literal["flag"] = "flag"


@dataclass(frozen=True)
class ToolArgProfileStringArg:
    name: str
    value: str
    type: Literal["string"] = "string"


@dataclass(frozen=True)
class ToolArgProfileFileArg:
    name: str
    path: str
    type: Literal["file"] = "file"


type ToolArgProfileArg = (
    ToolArgProfileFlagArg | ToolArgProfileStringArg | ToolArgProfileFileArg
)


@dataclass(frozen=True)
class ToolArgProfile:
    id: int
    tool_name: str
    name: str
    args: list[ToolArgProfileArg]
    created_at: str
    updated_at: str
