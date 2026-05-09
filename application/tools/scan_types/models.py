"""Application-layer dataclass for scan type strategy configuration."""

from __future__ import annotations

from dataclasses import dataclass, field

from application.ports.user_prompt import UserPromptPort
from domain.tools.execution_config import ToolExecutionConfig


@dataclass
class ScanTypeConfig:
    project_name: str
    base_path: str
    tool_config: ToolExecutionConfig
    run_id: int | None
    prompt: UserPromptPort
    remaining_peers: int = 0
    project_id: int | None = None
    arg_snapshots: dict[str, str] = field(default_factory=dict)
