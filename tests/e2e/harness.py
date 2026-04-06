"""TallyHarness — drive the tally REPL via a PTY for debugging and e2e tests.

Usage (debugging, against the real repo):

    from tests.e2e.harness import TallyHarness
    h = TallyHarness()
    h.spawn()
    print(h.run("project list"))
    h.teardown()

Usage (isolated test environment):

    h = TallyHarness(base_path=tmp_path)
    h.setup()   # copies global.json, confirms attestation
    h.spawn()
    ...
    h.teardown()

Context-manager form (tears down automatically):

    with TallyHarness(base_path=tmp_path) as h:
        h.setup()
        h.spawn()
        output = h.run("project list")
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import date
from os import _Environ
from pathlib import Path
from typing import cast

import pexpect

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TALLY_ROOT = Path(__file__).resolve().parents[2]
_VENV_PYTHON = TALLY_ROOT / ".venv" / "bin" / "python3"
_TALLY_SCRIPT = TALLY_ROOT / "tally.py"

# Strip ANSI escape sequences from captured output.
_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

# When TALLY_HARNESS=1 the REPL skips prompt_toolkit and emits this sentinel
# to stdout before waiting for each command.  pexpect matches on it so there
# is no dependency on prompt_toolkit's PTY rendering.
PROMPT = r"__TALLY_PROMPT__"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip(text: str) -> str:
    """Remove ANSI escape codes and strip surrounding whitespace."""
    return _ANSI.sub("", text).strip()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class TallyHarness:
    """Control the tally REPL process and inspect its side-effects."""

    def __init__(
        self,
        base_path: Path | None = None,
        timeout: int = 30,
    ) -> None:
        """
        Args:
            base_path: Root directory for config / projects / logs.
                       Defaults to the real repo root (no isolation).
            timeout:   Default pexpect timeout in seconds.
        """
        self.base_path = base_path or TALLY_ROOT
        self.default_timeout = timeout
        self.child: pexpect.spawn | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Prepare an isolated environment under self.base_path.

        Copies config/global.json from the real repo and ensures
        location_attestation_confirmed is True so the REPL starts
        without an interactive prompt.  No-op when base_path is the
        real repo root (attestation is already stored there).
        """
        if self.base_path == TALLY_ROOT:
            return

        real_cfg = TALLY_ROOT / "config" / "global.json"
        if not real_cfg.exists():
            raise FileNotFoundError(
                f"Real config not found at {real_cfg}. "
                "Cannot set up isolated harness environment."
            )

        config_dir = self.base_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        dest_cfg = config_dir / "global.json"
        shutil.copy(real_cfg, dest_cfg)

        with open(dest_cfg) as fh:
            data = json.load(fh)
        data["location_attestation_confirmed"] = True
        with open(dest_cfg, "w") as fh:
            json.dump(data, fh, indent=2)

    def spawn(self, extra_args: list[str] | None = None) -> None:
        """Spawn the tally process and wait for the first REPL prompt.

        Args:
            extra_args: Additional CLI arguments forwarded to tally.py.
        """
        args: list[str] = [
            str(_TALLY_SCRIPT),
            "--skip-checks",
            f"--base-path={self.base_path}",
        ]
        if extra_args:
            args.extend(extra_args)

        env = cast(_Environ[str], {**os.environ, "TALLY_HARNESS": "1"})
        self.child = pexpect.spawn(
            str(_VENV_PYTHON),
            args,
            cwd=str(TALLY_ROOT),
            encoding="utf-8",
            codec_errors="replace",
            timeout=self.default_timeout,
            env=env,
        )
        # Block until the first prompt sentinel is ready.
        self.child.expect(PROMPT, timeout=self.default_timeout)

    def teardown(self) -> None:
        """Send 'exit' and wait for the process to terminate cleanly."""
        if self.child and self.child.isalive():
            try:
                self.child.sendline("exit")
                self.child.expect(pexpect.EOF, timeout=5)
            except Exception:
                self.child.terminate(force=True)
        self.child = None

    def __enter__(self) -> TallyHarness:
        return self

    def __exit__(self, *_: object) -> None:
        self.teardown()

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def send(self, text: str) -> None:
        """Send a line of text to stdin without waiting for a response.

        Use this when the next output is a wizard prompt rather than the
        REPL prompt — follow it with expect() or expect_prompt().
        """
        assert self.child is not None, "Call spawn() first"
        self.child.sendline(text)

    def run(self, cmd: str, timeout: int | None = None) -> str:
        """Send a REPL command, wait for the next prompt, return output.

        The returned string has ANSI codes stripped and leading/trailing
        whitespace removed.  It includes everything the REPL printed
        between the command echo and the next prompt.
        """
        self.send(cmd)
        return self.wait_for_prompt(timeout)

    def wait_for_prompt(self, timeout: int | None = None) -> str:
        """Block until the REPL prompt appears; return preceding output."""
        assert self.child is not None, "Call spawn() first"
        self.child.expect(PROMPT, timeout=timeout or self.default_timeout)
        return _strip(self.child.before or "")

    def expect(self, pattern: str, timeout: int | None = None) -> str:
        """Wait for *pattern* (regex) and return before+after, stripped.

        Raises pexpect.TIMEOUT if the pattern is not seen in time, which
        will surface as a test failure with a useful message.
        """
        assert self.child is not None, "Call spawn() first"
        self.child.expect(pattern, timeout=timeout or self.default_timeout)
        before = _strip(self.child.before or "")
        after = _strip(self.child.after if isinstance(self.child.after, str) else "")
        return before + after

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def query_db(
        self,
        project: str,
        sql: str,
        params: tuple = (),
    ) -> list[dict]:
        """Execute SQL against a project's findings.db.

        Returns a list of dicts (one per row).  The database must exist
        — run at least one scan first if you need findings data.

        Example:
            rows = h.query_db(
                "myproject",
                "SELECT tool, count(*) as n FROM findings GROUP BY tool",
            )
        """
        db = self.base_path / "projects" / project / "sqlite" / "findings.db"
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def read_log(self, errors_only: bool = False) -> str:
        """Return today's application log (or the error-only log).

        Logs are written to <repo-root>/logs/ regardless of base_path.
        """
        prefix = "errors-" if errors_only else ""
        log = TALLY_ROOT / "logs" / f"{prefix}{date.today()}.log"
        return log.read_text() if log.exists() else ""

    def read_file(self, path: Path) -> str:
        """Return the contents of *path* as a string."""
        return path.read_text()

    def project_dir(self, project: str) -> Path:
        """Return the project root directory under base_path."""
        return self.base_path / "projects" / project

    def db_path(self, project: str) -> Path:
        """Return the path to a project's findings.db."""
        return self.project_dir(project) / "sqlite" / "findings.db"
