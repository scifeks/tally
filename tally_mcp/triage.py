"""Triage orchestration — TriageResult and TriageRunner."""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from core.store.sqlite_store import SQLiteStore

from .config import SESSION_TIMEOUT_SECONDS
from .prompts import api_trace as _api_trace
from .prompts import code_trace as _code_trace
from .prompts import dependency as _dependency
from .prompts import enrich_only as _enrich_only

_log = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).parent.parent

TOOL_STRATEGY: dict[str, str] = {
    "semgrep": "code_trace",
    "zap": "api_trace",
    "osv-scanner": "dependency",
    "pip-audit": "dependency",
    "npm-audit": "dependency",
    "composer-audit": "dependency",
    "gitleaks": "enrich_only",
    "nmap": "skip",
    "tree-sitter": "skip",
}

STRATEGY_PROMPT: dict[str, object] = {
    "code_trace": _code_trace.render,
    "api_trace": _api_trace.render,
    "dependency": _dependency.render,
    "enrich_only": _enrich_only.render,
}

_AUDIT_WRITE_TOOLS = ("update_finding", "update_findings_batch")


@dataclass
class TriageResult:
    sessions_run: int
    success: int
    failed: int
    incomplete: int


class TriageRunner:
    def __init__(self, project: str, store: SQLiteStore, app_root: Path) -> None:
        self._project = project
        self._store = store
        self._app_root = app_root

    @classmethod
    def for_project(cls, project: str, app_root: Path | None = None) -> TriageRunner:
        root = app_root or _APP_ROOT
        db = root / "projects" / project / "sqlite" / "findings.db"
        if not db.exists():
            raise FileNotFoundError(f"Project database not found: {db}")
        store = SQLiteStore(root, project)
        return cls(project, store, root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def batch(self) -> tuple[int, int]:
        """Run batching phase only.

        Returns (run_id, total_batches_created).
        """
        run_id = self._store.create_run({})

        reset_count = self._store.reset_stale_triage_batches(run_id)
        if reset_count:
            _log.info(
                "Reset %d stale in_progress batches for run_id=%d",
                reset_count,
                run_id,
            )

        skip_tools = frozenset(t for t, s in TOOL_STRATEGY.items() if s == "skip")
        combos = self._store.get_active_finding_combos(skip_tools)

        total = 0
        for tool, repo, segment in combos:
            try:
                count = self._store.create_triage_batches(run_id, tool, repo, segment)
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
        self.batch()

        findings = self._store.get_untriaged_findings()

        strategy_batches: dict[str, list[int]] = {}
        skipped = 0
        for finding_id, tool in findings:
            strategy = TOOL_STRATEGY.get(tool or "", "enrich_only")
            if strategy == "skip":
                skipped += 1
                continue
            strategy_batches.setdefault(strategy, []).append(finding_id)

        if skipped:
            _log.info("Skipped %d findings with skip-strategy tools", skipped)

        mcp_json_path = self._write_mcp_config()

        sessions_run = success = failed = incomplete = 0
        try:
            for strategy, finding_ids in strategy_batches.items():
                sessions_run += 1
                outcome = self._run_session(strategy, finding_ids)
                if outcome == "success":
                    success += 1
                elif outcome == "failed":
                    failed += 1
                else:
                    incomplete += 1
        finally:
            mcp_json_path.unlink(missing_ok=True)

        return TriageResult(
            sessions_run=sessions_run,
            success=success,
            failed=failed,
            incomplete=incomplete,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_session(self, strategy: str, finding_ids: list[int]) -> str:
        """Run one Claude session. Returns 'success', 'failed', or 'incomplete'."""
        render_fn = STRATEGY_PROMPT[strategy]
        prompt_text = render_fn(finding_ids, self._project)  # type: ignore[operator]
        session_start = datetime.now(UTC).isoformat()

        try:
            result = subprocess.run(
                [
                    "claude",
                    "--print",
                    "--dangerously-skip-permissions",
                    prompt_text,
                ],
                capture_output=True,
                text=True,
                timeout=SESSION_TIMEOUT_SECONDS,
                cwd=str(self._app_root),
            )
        except subprocess.TimeoutExpired:
            _log.error(
                "Triage session timed out after %ds (strategy=%s)",
                SESSION_TIMEOUT_SECONDS,
                strategy,
            )
            return "failed"
        except Exception as exc:
            _log.error(
                "Subprocess error during triage (strategy=%s): %s",
                strategy,
                exc,
            )
            return "failed"

        if result.returncode != 0:
            _log.error(
                "Triage session failed (strategy=%s, rc=%d): %s",
                strategy,
                result.returncode,
                result.stderr,
            )
            return "failed"

        updated_count = self._store.count_audit_events_since(
            _AUDIT_WRITE_TOOLS, session_start
        )
        if updated_count > 0:
            _log.info(
                "Triage session success (strategy=%s, updates=%d)",
                strategy,
                updated_count,
            )
            return "success"

        _log.warning(
            "Session completed but no findings updated — "
            "possible prompt failure or empty batch (strategy=%s)",
            strategy,
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
                }
            }
        }
        mcp_json_path.write_text(json.dumps(payload, indent=2))
        return mcp_json_path
