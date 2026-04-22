import logging
import os
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, NamedTuple

from application.ports.user_prompt import UserPromptPort
from domain.tools.base import ToolResult, ToolWrapper
from domain.tools.interface import ExecutionPass

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


def sanitize_command(cmd: list[str]) -> list[str]:
    """Raise ValueError if any token in *cmd* looks like a shell injection attempt."""
    for token in cmd:
        if token in _METACHAR_TOKENS:
            raise ValueError(f"Unsafe shell operator in command: {token!r}")
        if any(ch in token for ch in _METACHAR_CHARS):
            raise ValueError(f"Shell metacharacter in command token: {token!r}")
    return cmd


class _RunResult(NamedTuple):
    proc: subprocess.CompletedProcess[str]
    start: float
    success: bool


class ToolExecutor:
    def __init__(
        self,
        project_name: str,
        base_path: Path,
        prompt: UserPromptPort,
    ) -> None:
        self.project_name = project_name
        self.base_path = Path(base_path)
        self._prompt = prompt
        self._sudo_approved = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        tool: ToolWrapper,
        auto_approve: bool | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        label: str = "output",
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """Build, approve, run, capture, and return a ToolResult.

        Args:
            tool:         The ToolWrapper to run.
            auto_approve: Pass True to bypass the approval prompt (used by
                          run() after execute_tool_passes has already obtained
                          per-tool consent).
            timeout:      Seconds before the subprocess is killed (default 300).
            label:        Prefix for saved output filenames (e.g. "webservers").
            cwd:          Working directory for the subprocess. Required for
                          tools like npm-audit and composer-audit that must run
                          inside the project directory.
            **kwargs:     Passed verbatim to tool.build_command().
        """
        timestamp = ToolResult.now_iso()

        # 1. Build command argv
        try:
            cmd = tool.build_command(**kwargs)
        except Exception as exc:
            _log.error("Tool %s: build_command error: %s", tool.name, exc)
            return self._failure(tool.name, timestamp, f"build_command error: {exc}")

        # 2. Basic safety check (no shell=True, but guard against obvious injections)
        try:
            sanitize_command(cmd)
        except ValueError as exc:
            _log.error("Tool %s: command sanitization failed: %s", tool.name, exc)
            return self._failure(tool.name, timestamp, str(exc))

        # 3. Human approval gate
        if not auto_approve:
            if not self._prompt_approval(tool.name, cmd):
                return self._failure(tool.name, timestamp, "Execution denied by user.")

        # 4. Run (with privilege escalation if needed)
        _log.info("Tool %s: command: %s", tool.name, shlex.join(cmd))
        if env:
            _log.info("Tool %s: env overrides: %s", tool.name, list(env.keys()))
        output_dir = self._ensure_output_dir(tool.name)
        ts_file = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")
        findings_exit_ok = getattr(tool, "findings_exit_ok", False)

        start = perf_counter()
        run_result = self._run_with_escalation(
            cmd, tool.name, timestamp, timeout, cwd, start, findings_exit_ok, env
        )
        if isinstance(run_result, ToolResult):
            return run_result
        proc, start, success = run_result
        duration = round(perf_counter() - start, 3)

        # 5. Persist stdout / stderr to disk
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

        # 6. Parse output (failures are silently swallowed — parsed_data stays None)
        parsed: dict[str, Any] | None = None
        try:
            parsed = tool.parse_output(combined, output_files)
        except Exception:
            _log.exception("Tool %s: parse_output raised an exception", tool.name)

        status = "✓ Complete" if success else "✗ Failed "
        print(f"    {status} (exit {proc.returncode}, {duration}s)")
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
            **pass_.kwargs,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_output_dir(self, tool_name: str) -> Path:
        path = (
            self.base_path / "projects" / self.project_name / "tool_outputs" / tool_name
        )
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _prompt_approval(self, tool_name: str, cmd: list[str]) -> bool:
        print()
        print("!!HUMAN APPROVAL REQUIRED!!")
        print(f"Tool:    {tool_name}")
        print(f"Command: {' '.join(cmd)}")
        return self._prompt.confirm("Approve execution?")

    def _prompt_sudo(self, tool_name: str, sudo_cmd: list[str]) -> bool:
        print()
        print(f"[{tool_name}] This scan type requires root privileges.")
        print(f"Command: {' '.join(sudo_cmd)}")
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

    @staticmethod
    def _timeout_result(
        tool_name: str, timestamp: str, start: float, timeout: int
    ) -> ToolResult:
        duration = round(perf_counter() - start, 3)
        _log.error("Tool %s: timed out after %ds", tool_name, timeout)
        print(f"    ✗ Failed  (timeout after {timeout}s)")
        return ToolResult(
            tool_name=tool_name,
            success=False,
            output=f"Timed out after {timeout} seconds.",
            parsed_data=None,
            output_files={},
            timestamp=timestamp,
            duration_seconds=duration,
        )

    def _run_subprocess(
        self,
        cmd: list[str],
        timeout: int,
        cwd: str | None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        import signal as _signal

        effective_env = {**os.environ, **env} if env else None
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=effective_env,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), _signal.SIGKILL)
            except ProcessLookupError:
                pass
            # Drain pipes so the OS buffers are freed, then re-raise so the
            # caller's TimeoutExpired handler fires as before.
            try:
                proc.communicate()
            except Exception:
                pass
            raise
        return subprocess.CompletedProcess(
            args=proc.args,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )

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
    ) -> _RunResult | ToolResult:
        try:
            proc = self._run_subprocess(cmd, timeout, cwd, env)
        except subprocess.TimeoutExpired:
            return self._timeout_result(tool_name, timestamp, start, timeout)
        except FileNotFoundError:
            print("    ✗ Failed  (command not found)")
            _log.error("Tool %s: command not found: %s", tool_name, cmd[0])
            return self._failure(tool_name, timestamp, f"Command not found: {cmd[0]!r}")
        except PermissionError:
            print("    ✗ Failed  (permission denied)")
            _log.error("Tool %s: permission denied: %s", tool_name, cmd[0])
            return self._failure(tool_name, timestamp, f"Permission denied: {cmd[0]!r}")

        success = proc.returncode == 0 or (findings_exit_ok and proc.returncode == 1)

        if not success and _needs_root(proc.stderr):
            sudo_cmd = ["sudo"] + cmd
            if self._sudo_approved or self._prompt_sudo(tool_name, sudo_cmd):
                self._sudo_approved = True
                start = perf_counter()
                try:
                    proc = self._run_subprocess(sudo_cmd, timeout, cwd, env)
                except subprocess.TimeoutExpired:
                    return self._timeout_result(tool_name, timestamp, start, timeout)
                except FileNotFoundError:
                    su_cmd = ["su", "-c", shlex.join(cmd)]
                    print("    (sudo not found, retrying with su -c...)")
                    start = perf_counter()
                    try:
                        proc = self._run_subprocess(su_cmd, timeout, cwd, env)
                    except subprocess.TimeoutExpired:
                        return self._timeout_result(
                            tool_name, timestamp, start, timeout
                        )
                    except (FileNotFoundError, PermissionError):
                        print("    ✗ Failed  (elevated privileges not available)")
                        _log.error(
                            "Tool %s: elevated privileges unavailable", tool_name
                        )
                        return self._failure(
                            tool_name,
                            timestamp,
                            "Elevated privileges not available"
                            " (sudo and su both failed)",
                        )
                except PermissionError:
                    print("    ✗ Failed  (permission denied)")
                    _log.error("Tool %s: permission denied running sudo", tool_name)
                    return self._failure(
                        tool_name, timestamp, "Permission denied running sudo"
                    )
                success = proc.returncode == 0

        return _RunResult(proc=proc, start=start, success=success)
