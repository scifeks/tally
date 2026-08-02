"""OpenCode-backed LLM-based codebase security scan adapter."""

from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from pathlib import Path

from application.ports.llm_scan_backend import (
    LlmScanResult,
    PreparedLlmScanSession,
)
from domain.findings.llm_parser import parse_llm_findings

_OC_CONFIG_PATH = "/etc/opencode/opencode.json"


class OpenCodeLlmScanAdapter:
    """OpenCode-backed LLM-based security scanner."""

    def __init__(
        self,
        *,
        compose_path: Path,
        model: str = "",
        provider_name: str = "ollama",
    ) -> None:
        self._compose_path = compose_path
        self._model = model
        self._provider_name = provider_name
        self.last_raw_output: str = ""

    @contextmanager
    def prepare_session(
        self,
        *,
        project: str,
        run_id: int,
        app_root: Path,
    ):
        yield PreparedLlmScanSession(cwd=app_root)

    def run_scan(
        self,
        prompt: str,
        *,
        timeout_seconds: int,
        cwd: Path,
    ) -> LlmScanResult:
        """Run an LLM-based security scan via OpenCode.

        Args:
            prompt: Input prompt describing what to scan for.
            timeout_seconds: Maximum time to wait for completion.
            cwd: Working directory for the scan.

        Returns:
            LlmScanResult with findings or error details.
        """
        cmd = [
            "docker",
            "compose",
            "-f",
            str(self._compose_path),
            "exec",
            "-T",
            "-e",
            f"OPENCODE_CONFIG={_OC_CONFIG_PATH}",
            "triage-agent",
            "opencode",
            "run",
            "--dangerously-skip-permissions",
            "--dir",
            "/workspace",
            "--format",
            "json",
        ]
        if self._model:
            cmd.extend(["--model", f"{self._provider_name}/{self._model}"])

        try:
            completed = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return LlmScanResult(
                success=False,
                findings=[],
                error=f"Scan timeout after {timeout_seconds}s",
            )

        self.last_raw_output = completed.stdout

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            error_msg = (
                f"opencode exited with code {completed.returncode}: {stderr[:200]}"
            )
            return LlmScanResult(
                success=False,
                findings=[],
                raw_output=completed.stdout,
                error=error_msg,
            )

        text = self._extract_text(completed.stdout)
        findings, parse_errors = parse_llm_findings(text)

        if parse_errors:
            error_msg = "; ".join(parse_errors[:3])
            return LlmScanResult(
                success=False,
                findings=findings,
                raw_output=completed.stdout,
                error=error_msg,
            )

        return LlmScanResult(
            success=True,
            findings=findings,
            raw_output=completed.stdout,
        )

    def _extract_text(self, stdout: str) -> str:
        """Extract text from NDJSON output.

        OpenCode outputs streaming NDJSON; we extract text events for LLM
        processing.
        """
        if not stdout.strip():
            return ""

        chunks: list[str] = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            if obj.get("type") != "text":
                continue
            part = obj.get("part")
            if isinstance(part, dict):
                txt = part.get("text")
                if isinstance(txt, str):
                    chunks.append(txt)

        return "".join(chunks)
