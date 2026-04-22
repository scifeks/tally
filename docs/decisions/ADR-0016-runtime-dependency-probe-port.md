# ADR-0016 — Runtime Dependency Probe Port

**Status:** Accepted  
**Date:** 2026-04-22  
**Deciders:** Scifeks  
**Influences:** TAL-94 (Claude Code CLI gating)  
**Related Decisions:** ADR-0011 (per-tool subprocess timeout reused for the
10-second probe budget)

---

## Context

The `triage` command shells out to the `claude` binary
(`application/triage/runner.py`).  If that binary is absent, triage fails
with an opaque subprocess error after the user has already paid the cost of
a full scan.

The problem is not isolated to Claude Code: future capabilities such as
`docker` (container-based scanners), `git` (SBOM derivation), and `ollama`
(local LLM enrichment) would create the same pattern of "runtime binary that
must be present for a subset of features to work."

Scanner tools (gitleaks, semgrep, ZAP, …) are already modelled via
`ToolInterface`/`check_available()`.  However, scanner tools are optional
add-ons selected by the user per project; runtime capabilities are platform
prerequisites that the application itself depends on.  Mixing these two axes
in `ToolInterface` or `DependencyChecker.check_system_tools()` would blur
the distinction and couple infrastructure concerns to user-facing tool
configuration.

The requirement is therefore to:

1. Detect the Claude Code CLI at REPL startup and list it in the
   "Installed System Tools" banner.
2. Grey out the `triage` help rows and gate every `triage` sub-command
   when the binary is missing.
3. Include Claude in `tally --check`; exit non-zero when missing.
4. Not block REPL startup — only triage is gated.
5. Expose a `GET /api/v1/runtime-dependencies` endpoint for the future
   web UI triage gate.

---

## Decision

Model runtime capabilities as a dedicated hexagonal layer distinct from
scanner tools:

### Domain port (`domain/runtime/`)

- `RuntimeDependencyRequirement` (frozen dataclass): `name`, `binary`,
  `install_hint`, `required_for`.
- `RuntimeDependencyStatus` (frozen dataclass): `name`, `installed`,
  `binary_path`, `version`, `install_hint`, `required_for`, `error`.
- `RuntimeDependencyProbe` (Protocol): single property `requirement` +
  single method `probe() -> RuntimeDependencyStatus`.  Pure contract; no I/O.

### Infrastructure adapter (`infrastructure/runtime/`)

- `ClaudeCodeProbe` implements `RuntimeDependencyProbe`.
- Two-step probe: `shutil.which("claude")` (PATH check), then
  `subprocess.run(["claude", "--version"], timeout=10)` with ANSI strip and
  semver regex (reusing the helpers from `infrastructure/tools/version.py`).
- Distinguishes PATH-miss from invocation failure in the `error` field.

### Application service (`application/runtime/`)

- `RuntimeDependencyService(probes: Sequence[RuntimeDependencyProbe])`.
- Probes once at construction; caches the result list.
- `statuses()`, `get(name)`, `is_installed(name)`, `refresh()`.

### Integration points

- `tally.py`: constructs `RuntimeDependencyService([ClaudeCodeProbe()])`
  once; passes it to `DependencyChecker` on `--check` (blocks on missing)
  and to `REPL` (gates triage, but does not block startup).
- `DependencyChecker.run()`: folds runtime statuses into the check result
  as `DepCheck(type="runtime_dep", required=True, …)`.
- `print_installed_system_tools`: accepts optional `runtime_deps` and appends
  rows to the existing scanner table.
- `HelpRenderer._build_table`: dims triage rows and prefixes descriptions
  with `[red](Claude Code required)[/red]` when Claude is missing.
- `TriageCommands.cmd_triage`: short-circuits before project/arg checks
  when Claude is missing.

---

## Alternatives Considered

### Special-case inside `DependencyChecker`

Inline `shutil.which("claude")` directly in `check_system_tools()`.

**Rejected:** `DependencyChecker` checks scanner tools that are optional
add-ons the user configures.  Conflating platform prerequisites with
optional scanners makes the distinction unreadable and would require adding
special-case logic each time a new runtime capability appears.

### Reuse `ToolInterface.check_available()`

Model Claude Code as a pseudo-tool and add it to the scanner wrappers.

**Rejected:** Scanner tools are user-selected, project-scoped, and produce
findings.  Claude Code is a platform dependency, is global, and produces no
findings.  Forcing it into `ToolInterface` would require a dummy `normalize`
method and would appear in the tool catalog, confusing users.

### Inline `shutil.which` at every call site

Gate triage by calling `shutil.which("claude")` in `TriageCommands` and
`HelpRenderer` independently.

**Rejected:** Duplicates I/O at every render and command boundary; provides
no single place to inject a test double; makes the `--check` integration
non-trivial; prevents reuse for future capabilities.

---

## Pros

- Clean separation of concerns: scanner tools vs. runtime capabilities.
- Single probe at startup; O(1) reads thereafter via the service cache.
- `refresh()` allows future dynamic re-check without restarting.
- Protocol-based design makes test doubles trivial (no subprocess patching
  required at integration-test boundaries).
- Reuses existing subprocess timeout convention (10 s, from ADR-0011).
- `GET /api/v1/runtime-dependencies` is a natural home for the future UI
  triage gate without touching the tool catalog endpoint.

## Cons

- Three new packages (`domain/runtime`, `infrastructure/runtime`,
  `application/runtime`) for what is currently one binary check.
- Service must be constructed before the REPL and threaded through several
  constructors, increasing wiring complexity slightly.

---

## Consequences

### Positive

- Any future runtime capability (ollama, docker, git) slots in by adding
  one `Probe` implementation and registering it with
  `RuntimeDependencyService` — no changes to `DependencyChecker` or the
  REPL layer.
- `tally --check` is now authoritative for both scanner availability and
  runtime capability; CI can rely on the exit code.

### Negative

- `RuntimeDependencyService` is constructed at `tally.py` entry and passed
  through constructors; adding a new runtime dep requires updating the
  construction site in `tally.py`.

### New Decisions Required

- When the web API is implemented, a decision is needed on whether
  `GET /api/v1/runtime-dependencies` re-probes on request or returns the
  cached startup result.  Current recommendation: return cached; expose a
  `POST /api/v1/runtime-dependencies/refresh` for operator-triggered
  re-probe.

---

## Review Date

2026-10-22 (six months).  Revisit if a second runtime dependency is added
before then, as the three-package structure may be over-engineered for a
single binary.
