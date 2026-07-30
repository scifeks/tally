import logging
import shlex
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, NamedTuple

from application.locking.cancellation import CancellationToken, no_op_token
from application.ports.progress_reporter import (
    NullProgressReporter,
    ProgressReporter,
)
from application.ports.subprocess_runner import (
    SubprocessCancelled,
    SubprocessNotFound,
    SubprocessPermissionDenied,
    SubprocessResult,
    SubprocessRunnerPort,
    SubprocessTimeout,
)
from application.ports.user_prompt import UserPromptPort
from core.project_paths import ProjectPaths
from domain.tools.base import ToolResult, ToolWrapper
from domain.tools.interface import ExecutionPass


class ToolCancelled(Exception):
    """Raised when a tool execution is interrupted via the cancellation token."""


_log = logging.getLogger(__name__)

# Tokens that are unambiguously shell operators
_METACHAR_TOKENS = {"&&", "||", ";", ">", ">>", "<", "<<", "|"}
# Characters that indicate shell-injection within a single token
_METACHAR_CHARS = frozenset(";&|<>`$")

DEFAULT_TIMEOUT = 10800  # seconds (3 hours)

_NEEDS_ROOT_PATTERNS = [
    "requires root privileges",
    "requires privileged access",
    "operation not permitted",
    "couldn't open a raw socket",
    "socket: operation not permitted",
    "quitting!",
]


def _needs_root(stderr: str) -> bool:
    low = stderr.lower()
    return any(pat in low for pat in _NEEDS_ROOT_PATTERNS)


def _sanitize_filename(label: str) -> str:
    for ch in ("://", "/", "\\", ":", "*", "?", '"', "<", ">", "|"):
        label = label.replace(ch, "_")
    return label


def sanitize_command(cmd: list[str]) -> list[str]:
    """Reject any token in cmd that looks like a shell injection."""
    for token in cmd:
        if token in _METACHAR_TOKENS:
            raise ValueError(f"Unsafe shell operator in command: {token!r}")
        if any(ch in token for ch in _METACHAR_CHARS):
            raise ValueError(f"Shell metacharacter in command token: {token!r}")
    return cmd


class _RunResult(NamedTuple):
    proc: SubprocessResult
    start: float
    success: bool


class ToolExecutor:
    def __init__(
        self,
        project_name: str,
        base_path: Path,
        prompt: UserPromptPort,
        subprocess_runner: SubprocessRunnerPort,
        reporter: ProgressReporter | None = None,
    ) -> None:
        self.project_name = project_name
        self.base_path = Path(base_path)
        self._prompt = prompt
        self._subprocess_runner = subprocess_runner
        self._reporter: ProgressReporter = reporter or NullProgressReporter()
        self._sudo_approved = False
        self._cancel_token: CancellationToken = no_op_token()

    def set_cancel_token(self, token: CancellationToken) -> None:
        """Install a cooperative cancellation flag for subprocess waits."""
        self._cancel_token = token

    # Public API

    def execute(
        self,
        tool: ToolWrapper,
        auto_approve: bool | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        label: str = "output",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        raw_cmd: list[str] | None = None,
        stdin_data: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """Build, approve, run, and capture a tool execution."""
        timestamp = ToolResult.now_iso()

        if raw_cmd is not None:
            cmd = raw_cmd
        else:
            try:
                cmd = tool.build_command(**kwargs)
            except Exception as exc:
                _log.error(
                    "Tool %s: build_command error: %s",
                    tool.name,
                    exc,
                )
                return self._failure(
                    tool.name,
                    timestamp,
                    f"build_command error: {exc}",
                )

        # Guard against argv injection even without shell=True
        try:
            sanitize_command(cmd)
        except ValueError as exc:
            _log.error("Tool %s: command sanitization failed: %s", tool.name, exc)
            return self._failure(tool.name, timestamp, str(exc))

        if not auto_approve:
            if not self._prompt_approval(tool.name, cmd):
                return self._failure(tool.name, timestamp, "Execution denied by user.")

        _log.info("Tool %s: command: %s", tool.name, shlex.join(cmd))
        if env:
            _log.info("Tool %s: env overrides: %s", tool.name, list(env.keys()))
        output_dir = self._ensure_output_dir(tool.name)
        ts_file = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        label = _sanitize_filename(label)
        findings_exit_ok = getattr(tool, "findings_exit_ok", False)

        start = perf_counter()
        run_result = self._run_with_escalation(
            cmd,
            tool.name,
            timestamp,
            timeout,
            cwd,
            start,
            findings_exit_ok,
            env,
            stdin_data,
        )
        if isinstance(run_result, ToolResult):
            return run_result
        proc, start, success = run_result
        duration = round(perf_counter() - start, 3)

        output_files: dict[str, Path] = {}
        if proc.stdout:
            path = output_dir / f"{label}_{ts_file}.stdout"
            path.write_text(proc.stdout, encoding="utf-8")
            output_files["stdout"] = path
        if proc.stderr:
            path = output_dir / f"{label}_{ts_file}.stderr"
            path.write_text(proc.stderr, encoding="utf-8")
            output_files["stderr"] = path

        # Combined output: stdout always first; append stderr on failure
        combined = proc.stdout or ""
        if not success and proc.stderr:
            combined = (combined + "\n" + proc.stderr).strip()

        parsed: dict[str, Any] | None = None
        try:
            parsed = tool.parse_output(combined, output_files)
        except Exception:
            _log.exception("Tool %s: parse_output raised an exception", tool.name)

        status = "✓ Complete" if success else "✗ Failed "
        self._reporter.report(f"    {status} (exit {proc.returncode}, {duration}s)")
        _log.info(
            "Tool %s: exit=%d duration=%.1fs", tool.name, proc.returncode, duration
        )
        if proc.stderr:
            _log.info("Tool %s stderr:\n%s", tool.name, proc.stderr[:5000])
        if proc.stdout and not success:
            _log.info("Tool %s stdout:\n%s", tool.name, proc.stdout[:5000])
        failure_output = proc.stderr or proc.stdout
        if not success and failure_output:
            _log.error(
                "Tool %s exited %d. output: %s",
                tool.name,
                proc.returncode,
                failure_output[:2000],
            )

        return ToolResult(
            tool_name=tool.name,
            success=success,
            output=combined,
            parsed_data=parsed,
            output_files=output_files,
            timestamp=timestamp,
            duration_seconds=duration,
        )

    def run(
        self,
        pass_: ExecutionPass,
        tool: Any,  # ToolInterface at runtime; Any avoids ToolWrapper type conflict
        auto_approve: bool = True,
    ) -> ToolResult:
        """Execute a single ExecutionPass."""
        tool_timeout: int = getattr(tool, "timeout", None) or DEFAULT_TIMEOUT
        return self.execute(
            tool,  # type: ignore[arg-type]
            auto_approve=auto_approve,
            timeout=tool_timeout,
            label=pass_.label_suffix,
            cwd=pass_.cwd,
            env=pass_.env,
            stdin_data=pass_.stdin_data,
            **pass_.kwargs,
        )

    def run_raw(
        self,
        raw_cmd: list[str],
        tool: Any,
        auto_approve: bool = True,
        label: str = "custom",
    ) -> ToolResult:
        """Execute a pre-built command, bypassing tool.build_command."""
        tool_timeout: int = getattr(tool, "timeout", None) or DEFAULT_TIMEOUT
        return self.execute(
            tool,
            auto_approve=auto_approve,
            timeout=tool_timeout,
            label=label,
            raw_cmd=raw_cmd,
        )

    # Private helpers

    def _ensure_output_dir(self, tool_name: str) -> Path:
        paths = ProjectPaths.from_canonical(self.base_path, self.project_name)
        path = paths.tool_output_dir(tool_name)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _prompt_approval(self, tool_name: str, cmd: list[str]) -> bool:
        self._reporter.report("")
        self._reporter.report("!!HUMAN APPROVAL REQUIRED!!")
        self._reporter.report(f"Tool:    {tool_name}")
        self._reporter.report(f"Command: {' '.join(cmd)}")
        return self._prompt.confirm("Approve execution?")

    def _prompt_sudo(self, tool_name: str, sudo_cmd: list[str]) -> bool:
        self._reporter.report("")
        self._reporter.report(f"[{tool_name}] This scan type requires root privileges.")
        self._reporter.report(f"Command: {' '.join(sudo_cmd)}")
        return self._prompt.confirm("Retry with sudo?")

    @staticmethod
    def _failure(tool_name: str, timestamp: str, message: str) -> ToolResult:
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=message,
            parsed_data=None,
            output_files={},
            timestamp=timestamp,
            duration_seconds=0.0,
        )

    def _timeout_result(
        self, tool_name: str, timestamp: str, start: float, timeout: int
    ) -> ToolResult:
        duration = round(perf_counter() - start, 3)
        _log.error("Tool %s: timed out after %ds", tool_name, timeout)
        self._reporter.report(f"    ✗ Failed  (timeout after {timeout}s)")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Timed out after {timeout} seconds.",
            parsed_data=None,
            output_files={},
            timestamp=timestamp,
            duration_seconds=duration,
        )

    def _spawn(
        self,
        cmd: list[str],
        timeout: int,
        cwd: str | None,
        env: dict[str, str] | None,
        stdin_data: str | None = None,
    ) -> SubprocessResult:
        """Delegate to the SubprocessRunner port; translate cancellation."""
        try:
            return self._subprocess_runner.run(
                cmd,
                timeout=timeout,
                cwd=cwd,
                env=env,
                cancel_token=self._cancel_token,
                stdin_data=stdin_data,
            )
        except SubprocessCancelled as exc:
            raise ToolCancelled from exc

    def _run_with_escalation(
        self,
        cmd: list[str],
        tool_name: str,
        timestamp: str,
        timeout: int,
        cwd: str | None,
        start: float,
        findings_exit_ok: bool,
        env: dict[str, str] | None = None,
        stdin_data: str | None = None,
    ) -> _RunResult | ToolResult:
        try:
            proc = self._spawn(cmd, timeout, cwd, env, stdin_data)
        except SubprocessTimeout:
            return self._timeout_result(tool_name, timestamp, start, timeout)
        except SubprocessNotFound:
            self._reporter.report("    ✗ Failed  (command not found)")
            _log.error("Tool %s: command not found: %s", tool_name, cmd[0])
            return self._failure(tool_name, timestamp, f"Command not found: {cmd[0]!r}")
        except SubprocessPermissionDenied:
            self._reporter.report("    ✗ Failed  (permission denied)")
            _log.error("Tool %s: permission denied: %s", tool_name, cmd[0])
            return self._failure(tool_name, timestamp, f"Permission denied: {cmd[0]!r}")

        success = proc.returncode == 0 or (findings_exit_ok and proc.returncode == 1)

        if not success and _needs_root(proc.stderr):
            sudo_cmd = ["sudo"] + cmd
            if self._sudo_approved or self._prompt_sudo(tool_name, sudo_cmd):
                self._sudo_approved = True
                start = perf_counter()
                try:
                    proc = self._spawn(sudo_cmd, timeout, cwd, env, stdin_data)
                except SubprocessTimeout:
                    return self._timeout_result(tool_name, timestamp, start, timeout)
                except SubprocessNotFound:
                    su_cmd = ["su", "-c", shlex.join(cmd)]
                    self._reporter.report(
                        "    (sudo not found, retrying with su -c...)"
                    )
                    start = perf_counter()
                    try:
                        proc = self._spawn(su_cmd, timeout, cwd, env, stdin_data)
                    except SubprocessTimeout:
                        return self._timeout_result(
                            tool_name, timestamp, start, timeout
                        )
                    except (SubprocessNotFound, SubprocessPermissionDenied):
                        self._reporter.report(
                            "    ✗ Failed  (elevated privileges not available)"
                        )
                        _log.error(
                            "Tool %s: elevated privileges unavailable", tool_name
                        )
                        return self._failure(
                            tool_name,
                            timestamp,
                            "Elevated privileges not available"
                            " (sudo and su both failed)",
                        )
                except SubprocessPermissionDenied:
                    self._reporter.report("    ✗ Failed  (permission denied)")
                    _log.error("Tool %s: permission denied running sudo", tool_name)
                    return self._failure(
                        tool_name, timestamp, "Permission denied running sudo"
                    )
                success = proc.returncode == 0

        return _RunResult(proc=proc, start=start, success=success)
