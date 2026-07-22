"""Application-layer dataclass for scan type strategy configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from application.ports.user_prompt import UserPromptPort
from domain.tools.execution_config import ToolExecutionConfig

if TYPE_CHECKING:
    from application.ports.git_diff import GitDiffPort
    from application.ports.project_repo_repository import (
        ProjectRepoRepositoryPort,
    )


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
    repo_repo: ProjectRepoRepositoryPort | None = None
    since_commit: str | None = None
    git_diff: GitDiffPort | None = None
