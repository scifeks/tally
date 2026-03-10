import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from .base import ToolResult, ToolWrapper

# Tokens that are unambiguously shell operators
_METACHAR_TOKENS = {"&&", "||", ";", ">", ">>", "<", "<<", "|"}
# Characters that indicate shell-injection within a single token
_METACHAR_CHARS = frozenset(";&|<>`$")

DEFAULT_TIMEOUT = 300  # seconds

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


class ToolExecutor:
    def __init__(
        self,
        project_name: str,
        base_path: Path,
        auto_approve: bool = False,
    ) -> None:
        self.project_name = project_name
        self.base_path = Path(base_path)
        self.auto_approve = auto_approve
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
        **kwargs,
    ) -> ToolResult:
        """Build, approve, run, capture, and return a ToolResult.

        Args:
            tool:         The ToolWrapper to run.
            auto_approve: Override instance-level auto_approve for this call.
            timeout:      Seconds before the subprocess is killed (default 300).
            label:        Prefix for saved output filenames (e.g. "webservers").
            cwd:          Working directory for the subprocess. Required for
                          tools like npm-audit and composer-audit that must run
                          inside the project directory.
            **kwargs:     Passed verbatim to tool.build_command().
        """
        timestamp = ToolResult.now_iso()
        effective_auto = self.auto_approve if auto_approve is None else auto_approve

        # 1. Build command argv
        try:
            cmd = tool.build_command(**kwargs)
        except Exception as exc:
            return self._failure(tool.name, timestamp, f"build_command error: {exc}")

        # 2. Basic safety check (no shell=True, but guard against obvious injections)
        try:
            sanitize_command(cmd)
        except ValueError as exc:
            return self._failure(tool.name, timestamp, str(exc))

        # 3. Human approval gate
        if not effective_auto:
            if not self._prompt_approval(tool.name, cmd):
                return self._failure(tool.name, timestamp, "Execution denied by user.")

        # 4. Run
        print(f"Running {tool.name}...")
        output_dir = self._ensure_output_dir(tool.name)
        ts_file = datetime.now(UTC).strftime("%Y-%m-%d_%H%M%S")

        start = perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            duration = round(perf_counter() - start, 3)
            print(f"✗ Failed  (timeout after {timeout}s)")
            return ToolResult(
                tool_name=tool.name,
                success=False,
                output=f"Timed out after {timeout} seconds.",
                parsed_data=None,
                output_files={},
                timestamp=timestamp,
                duration_seconds=duration,
            )
        except FileNotFoundError:
            print("✗ Failed  (command not found)")
            return self._failure(tool.name, timestamp, f"Command not found: {cmd[0]!r}")
        except PermissionError:
            print("✗ Failed  (permission denied)")
            return self._failure(tool.name, timestamp, f"Permission denied: {cmd[0]!r}")

        duration = round(perf_counter() - start, 3)
        success = proc.returncode == 0

        # 4b. Sudo retry if the failure looks like a privilege error
        if not success and _needs_root(proc.stderr):
            sudo_cmd = ["sudo"] + cmd
            if self._sudo_approved or self._prompt_sudo(tool.name, sudo_cmd):
                self._sudo_approved = True
                start = perf_counter()
                try:
                    proc = subprocess.run(
                        sudo_cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        cwd=cwd,
                    )
                except subprocess.TimeoutExpired:
                    duration = round(perf_counter() - start, 3)
                    print(f"✗ Failed  (timeout after {timeout}s)")
                    return ToolResult(
                        tool_name=tool.name,
                        success=False,
                        output=f"Timed out after {timeout} seconds.",
                        parsed_data=None,
                        output_files={},
                        timestamp=timestamp,
                        duration_seconds=duration,
                    )
                except FileNotFoundError:
                    # sudo not found — fall back to su -c
                    su_cmd = ["su", "-c", shlex.join(cmd)]
                    print("  (sudo not found, retrying with su -c...)")
                    start = perf_counter()
                    try:
                        proc = subprocess.run(
                            su_cmd,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            cwd=cwd,
                        )
                    except subprocess.TimeoutExpired:
                        duration = round(perf_counter() - start, 3)
                        print(f"✗ Failed  (timeout after {timeout}s)")
                        return ToolResult(
                            tool_name=tool.name,
                            success=False,
                            output=f"Timed out after {timeout} seconds.",
                            parsed_data=None,
                            output_files={},
                            timestamp=timestamp,
                            duration_seconds=duration,
                        )
                    except (FileNotFoundError, PermissionError):
                        print("✗ Failed  (elevated privileges not available)")
                        return self._failure(
                            tool.name,
                            timestamp,
                            "Elevated privileges not available"
                            " (sudo and su both failed)",
                        )
                except PermissionError:
                    print("✗ Failed  (permission denied)")
                    return self._failure(
                        tool.name, timestamp, "Permission denied running sudo"
                    )
                duration = round(perf_counter() - start, 3)
                success = proc.returncode == 0

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
            pass

        status = "✓ Complete" if success else "✗ Failed "
        print(f"{status} (exit {proc.returncode}, {duration}s)")

        return ToolResult(
            tool_name=tool.name,
            success=success,
            output=combined,
            parsed_data=parsed,
            output_files=output_files,
            timestamp=timestamp,
            duration_seconds=duration,
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

    @staticmethod
    def _prompt_approval(tool_name: str, cmd: list[str]) -> bool:
        print()
        print("!!HUMAN APPROVAL REQUIRED!!")
        print(f"Tool:    {tool_name}")
        print(f"Command: {' '.join(cmd)}")
        try:
            answer = input("Approve execution? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

    @staticmethod
    def _prompt_sudo(tool_name: str, sudo_cmd: list[str]) -> bool:
        print()
        print(f"[{tool_name}] This scan type requires root privileges.")
        print(f"Command: {' '.join(sudo_cmd)}")
        try:
            answer = input("Retry with sudo? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer in ("y", "yes")

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
