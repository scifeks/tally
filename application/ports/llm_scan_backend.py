"""Port for LLM-based codebase security scanning."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PreparedLlmScanSession:
    cwd: Path


@dataclass
class LlmFinding:
    file_path: str
    description: str
    severity: str
    confidence: str
    finding_type: list[str]
    segment: str
    reasoning: str = ""
    remediation: str = ""
    rule_id: str = ""
    line_number: int | None = None
    cwe: list[str] = field(default_factory=list)
    attack_vector: str = ""
    code_snippet: str = ""


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
