"""Serializable job specs the host sends to sdk-runner.py."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TriageJobSpec:
    model: str
    system_prompt: str
    user_prompt: str
    allowed_tools: list[str]
    cwd: str
    timeout_seconds: int
    mode: str = "triage"


@dataclass(frozen=True)
class ScanJobSpec:
    model: str
    user_prompt: str
    allowed_tools: list[str]
    cwd: str
    timeout_seconds: int
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    mode: str = "scan"


JobSpec = TriageJobSpec | ScanJobSpec


def serialize_spec(spec: JobSpec) -> str:
    return json.dumps(asdict(spec))
