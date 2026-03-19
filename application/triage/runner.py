"""Triage orchestration — TriageResult and TriageRunner."""

from __future__ import annotations

import importlib
import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.config.manager import ConfigManager as _ConfigManager
from core.tools.registry import tool_registry

try:
    _cfg = _ConfigManager(str(Path(__file__).parent.parent.parent)).global_config
    SESSION_TIMEOUT_SECONDS: int = _cfg.mcp_session_timeout_seconds
except FileNotFoundError:
    SESSION_TIMEOUT_SECONDS = 300

if TYPE_CHECKING:
    from core.store.repositories.audit import AuditRepository
    from core.store.repositories.runs import RunRepository
    from core.store.repositories.triage import TriageBatchRepository

_log = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).parent.parent.parent

_AUDIT_WRITE_TOOLS = ("update_finding", "update_findings_batch")


@dataclass
class TriageResult:
    sessions_run: int
    success: int
    failed: int
    incomplete: int


class TriageRunner:
    def __init__(
        self,
        project: str,
        run_repo: RunRepository,
        triage_repo: TriageBatchRepository,
        audit_repo: AuditRepository,
        app_root: Path,
    ) -> None:
        self._project = project
        self._run_repo = run_repo
        self._triage_repo = triage_repo
        self._audit_repo = audit_repo
        self._app_root = app_root

    @classmethod
    def for_project(cls, project: str, app_root: Path | None = None) -> TriageRunner:
        root = app_root or _APP_ROOT
        db = root / "projects" / project / "sqlite" / "findings.db"
        if not db.exists():
            raise FileNotFoundError(f"Project database not found: {db}")
        from core.store import make_store

        run_repo, _, triage_repo, audit_repo = make_store(root, project)
        return cls(project, run_repo, triage_repo, audit_repo, root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def batch(self) -> tuple[int, int]:
        """Run batching phase only.

        Returns (run_id, total_batches_created).
        """
        run_id = self._run_repo.create_run({})

        reset_count = self._triage_repo.reset_stale_batches(run_id)
        if reset_count:
            _log.info(
                "Reset %d stale in_progress batches for run_id=%d",
                reset_count,
                run_id,
            )

        skip_tools = frozenset(
            t.name for t in tool_registry.get_all_tools() if getattr(t, "skip", False)
        )
        combos = self._triage_repo.get_active_finding_combos(skip_tools)

        total = 0
        for tool, repo, segment in combos:
            try:
                count = self._triage_repo.create_batches(run_id, tool, repo, segment)
                _log.info(
                    "Created %d batches: tool=%s repo=%s segment=%s",
                    count,
                    tool,
                    repo,
                    segment,
                )
                print(f"  Batched {count} batch(es) for {tool}/{repo}/{segment}")
                total += count
            except Exception as exc:
                raise RuntimeError(
                    f"Batching failed for {tool}/{repo}/{segment}: {exc}"
                ) from exc
        return run_id, total

    def run(self) -> TriageResult:
        """Run full triage pipeline (batch → MCP setup → Claude sessions)."""
        run_id, _total = self.batch()
        mcp_json_path = self._write_mcp_config()
        try:
            return self._run_batch_loop(
                run_id,
                lambda batch_id, render_fn, finding_ids: self._run_session(
                    render_fn, finding_ids
                ),
            )
        finally:
            mcp_json_path.unlink(missing_ok=True)

    def run_dry_run(self) -> int:
        """Batch phase + render prompts to DEBUG log. No MCP server, no Claude.

        Returns the number of non-skip batches processed.
        """
        run_id, _total = self.batch()

        def _handler(
            batch_id: int,
            render_fn: Callable[..., str],
            finding_ids: list[int],
        ) -> str:
            prompt_text = render_fn(finding_ids, self._project)
            _log.debug(
                "========== BATCH %d (%d findings) ==========\n%s\n"
                "========== END BATCH %d ==========",
                batch_id,
                len(finding_ids),
                prompt_text,
                batch_id,
            )
            return "success"

        result = self._run_batch_loop(run_id, _handler)
        return result.sessions_run

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_batch_loop(
        self,
        run_id: int,
        handler: Callable[[int, Callable[..., str], list[int]], str],
    ) -> TriageResult:
        """Claim and process every pending batch for run_id.

        handler(batch_id, render_fn, finding_ids) -> outcome string.
        Skip-flagged tools are auto-completed without calling handler.
        """
        sessions_run = success = failed = incomplete = 0
        while True:
            batch = self._triage_repo.claim_batch(run_id)
            if batch is None:
                break

            batch_id: int = batch["id"]
            finding_ids: list[int] = batch["finding_ids"]
            batch_data: list[dict] = batch["batch_data"]

            tool_name = batch_data[0]["tool"] if batch_data else None
            tool_obj = tool_registry.get_tool(tool_name or "") if tool_name else None

            if tool_obj is None or tool_obj.skip:
                self._triage_repo.complete_batch(batch_id, "success")
                continue

            segment = tool_obj.scan_segment
            module = importlib.import_module(
                f"application.triage.prompts.{segment}_trace"
            )
            render_fn: Callable[..., str] = module.render

            sessions_run += 1
            outcome = handler(batch_id, render_fn, finding_ids)
            self._triage_repo.complete_batch(batch_id, outcome)

            if outcome == "success":
                success += 1
            elif outcome == "failed":
                failed += 1
            else:
                incomplete += 1

        return TriageResult(
            sessions_run=sessions_run,
            success=success,
            failed=failed,
            incomplete=incomplete,
        )

    def _run_session(
        self, render_fn: Callable[..., str], finding_ids: list[int]
    ) -> str:
        """Run one Claude session. Returns 'success', 'failed', or 'incomplete'."""
        prompt_text = render_fn(finding_ids, self._project)
        session_start = datetime.now(UTC).isoformat()

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    "--disallowedTools",
                    "Bash,Write,Edit,MultiEdit,WebFetch,WebSearch",
                ],
                input=prompt_text,
                capture_output=True,
                text=True,
                timeout=SESSION_TIMEOUT_SECONDS,
                cwd=str(self._app_root),
            )
        except subprocess.TimeoutExpired:
            _log.error(
                "Triage session timed out after %ds",
                SESSION_TIMEOUT_SECONDS,
            )
            return "failed"
        except Exception as exc:
            _log.error("Subprocess error during triage: %s", exc)
            return "failed"

        if result.returncode != 0:
            _log.error(
                "Triage session failed (rc=%d): %s",
                result.returncode,
                result.stderr,
            )
            return "failed"

        updated_count = self._audit_repo.count_events_since(
            _AUDIT_WRITE_TOOLS, session_start
        )
        if updated_count > 0:
            _log.info(
                "Triage session success (updates=%d)",
                updated_count,
            )
            return "success"

        _log.warning(
            "Session completed but no findings updated — "
            "possible prompt failure or empty batch"
        )
        return "incomplete"

    def _write_mcp_config(self) -> Path:
        """Write .mcp.json for Claude's MCP server and return its path."""
        mcp_json_path = self._app_root / ".mcp.json"
        venv_python = self._app_root / ".venv" / "bin" / "python"

        if not venv_python.exists():
            raise RuntimeError(f"Venv Python not found at {venv_python}")

        payload = {
            "mcpServers": {
                "tally-mcp": {
                    "type": "stdio",
                    "command": str(venv_python),
                    "args": [
                        "-m",
                        "tally_mcp.server",
                        "--project",
                        self._project,
                    ],
                    "permissions": {
                        "allow": ["get_findings_batch", "update_findings_batch"],
                        "deny": ["*"],
                    },
                }
            }
        }
        mcp_json_path.write_text(json.dumps(payload, indent=2))
        return mcp_json_path
