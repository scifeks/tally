"""Port for LLM-based codebase security scanning."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from domain.findings.llm_finding import LlmFinding


@dataclass(frozen=True)
class PreparedLlmScanSession:
    cwd: Path


@dataclass(frozen=True)
class LlmScanResult:
    success: bool
    findings: list[LlmFinding]
    raw_output: str = ""
    error: str | None = None


@runtime_checkable
class LlmScanBackendPort(Protocol):
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ) -> AbstractContextManager[PreparedLlmScanSession]: ...

    def run_scan(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> LlmScanResult: ...
