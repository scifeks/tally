# ADR-0011: Per-Tool Subprocess Timeouts via ToolInterface.timeout

## Status
Accepted

## Date
2026-03-27

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

`ToolExecutor` had a single hardcoded `DEFAULT_TIMEOUT = 300` (5 minutes) applied to
every subprocess call. On large repositories, gitleaks exceeded this limit — the `dir`
pass timed out, produced a failure result, then the `git` pass (which runs independently)
completed successfully. The terminal output was misleading:

```
✗ Failed  (timeout after 300s)
Running gitleaks...
✓ Complete (exit 0, 36.448s)
✓ gitleaks  | 158 findings | 336.5s
```

The tool succeeded overall only because `merge_pass_results` combined both passes, and
`findings_exit_ok = True` normalised the outcome. The first pass silently lost its
findings. Additionally, when a timeout occurred, there was nothing in the application
logs to identify which command had been running — gitleaks stderr (which contains finding
counts and scan status) was only logged on failure.

nmap has the same risk profile: a comprehensive `-sV -sC -O` scan across many hosts or
slow networks can far exceed 5 minutes per profile.

---

## Decision

**Timeout**: `ToolInterface` exposes an optional `timeout` property (default `None`).
When `None`, the executor falls back to `DEFAULT_TIMEOUT`. `ToolExecutor.run()` reads
`getattr(tool, "timeout", None) or DEFAULT_TIMEOUT` before calling `execute()`, so the
per-tool value is used end-to-end without changing the `execute()` signature.

Current values:
- `DEFAULT_TIMEOUT = 10800` — 3 hours (executor fallback for all unoverridden tools)
- `BaseGitleaksTool.timeout = 7200` — 2 hours per pass (dir and git are independent)
- `BaseNmapTool.timeout = 14400` — 4 hours per profile pass

The timeout is per-`ExecutionPass` (one subprocess call). Tools with multiple passes
(gitleaks runs two: `dir` + `git`; nmap runs one per profile) each get the full budget
independently. There is no global wall-clock limit across all passes or tools in a scan.

**Logging**: Three gaps were closed in `ToolExecutor`:
1. `_log.info("Tool %s: command: %s", ...)` is emitted immediately before each subprocess
   starts. If the process times out, the log contains the exact command that was running.
2. `_log.error("Tool %s: timed out after %ds", ...)` is emitted inside `_timeout_result()`
   so the timeout is visible in the application log without inspecting terminal output.
3. `if proc.stderr: _log.info("Tool %s stderr:\n%s", ...)` is emitted after every
   subprocess completes (success or failure). gitleaks writes `INF leaks found: N` and
   scan progress to stderr; this surfaces that output in the application log rather than
   only in the `.stderr` file on disk.

---

## Alternatives Considered

### Single global timeout increase
Replace `DEFAULT_TIMEOUT = 300` with a larger value (e.g. 4 hours) applied uniformly
to all tools.

**Rejected because**: a 4-hour global timeout hides the fact that gitleaks and nmap have
legitimately different requirements from short-running tools like pip-audit or npm-audit.
Per-tool overrides make the intent explicit and allow each tool's author to set a
defensible upper bound based on known scan characteristics.

### Configurable timeout in config/commands.json
Allow operators to override timeouts per-deployment without code changes.

**Rejected because**: the tool authors are best placed to set a safe upper bound, and the
per-class override in the base wrapper is the right place for that knowledge. The per-class
default already accommodates realistic worst-case scans. Operator-level overrides can be
added later if deployment-specific tuning proves necessary.

### Streaming subprocess with real-time logging
Replace buffered subprocess execution with a streaming approach that surfaces gitleaks
progress as it runs rather than only at completion.

**Rejected because**: streaming requires `asyncio` or threads in the executor, adding
substantial complexity. The primary need was post-hoc diagnosis from logs — knowing which
command was running when the timeout occurred. The three log additions achieve this
without architectural changes to the executor.

---

## Pros

- The timeout budget for each tool is explicit and documented in its base wrapper class,
  not hidden in a global constant.
- Timeout events are now visible in the application log with the exact command that timed
  out, enabling post-hoc diagnosis without terminal inspection.
- gitleaks stderr output (finding counts, scan progress) is captured in the application
  log after every run, not only on failure.
- Any new tool inherits a generous 3-hour default without needing to override `timeout`;
  only tools with known slow characteristics need an explicit override.

---

## Cons

- The timeout is per-pass, not per-tool or per-scan. A 3-tool scan where each tool has
  2 passes could theoretically run for `3 × 2 × DEFAULT_TIMEOUT` = 18 hours in the
  worst case. This is intentional, but means there is no global scan wall-clock limit.
- The `getattr(tool, "timeout", None) or DEFAULT_TIMEOUT` pattern in `ToolExecutor.run()`
  is a duck-typed fallback rather than a required interface method. A tool class that
  accidentally shadows `timeout` with a non-numeric attribute would silently use the
  default rather than raising at configuration time.

---

## Consequences

### Positive
- A gitleaks `git` pass on a repo with deep history now has a 2-hour budget. The single
  place to adjust this is `BaseGitleaksTool.timeout`.
- The first pass of gitleaks (`dir`) no longer silently drops findings when scanning
  large repositories under the old 5-minute default.

### Negative
- The total worst-case scan duration is unbounded at the pipeline level. There is no
  mechanism to abort a scan that has been running for an unreasonable wall-clock time.

### New Decisions Required
- A decision is needed on whether a global scan wall-clock limit should be introduced
  at the pipeline level, separate from per-pass timeouts.
- A decision is needed on whether operator-level timeout overrides via configuration
  are warranted, particularly for CI/CD environments with strict pipeline time budgets.

---

## Influences

- The gitleaks timeout incident on a large repository where the `dir` pass exceeded
  300 seconds and silently dropped findings, while the terminal reported overall success.
- TAL-98 branch, which introduced the fix alongside the logging improvements.

---

## Related Decisions

- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — `ToolInterface` is the interface extended with the `timeout` property

---

## Review Date

Review if operator-level timeout configuration is requested, or if a global scan
wall-clock limit is introduced that would interact with per-pass timeouts.
