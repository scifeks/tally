# ADR-0012: Noir as Pre-DAST Step with OAS3 File Passthrough to ZAP

## Status
Accepted

## Date
2026-04-03

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

OWASP ZAP's quick-scan mode (`-quickurl`) crawls a running application. For REST APIs,
crawler-based discovery misses endpoints that are not reachable from a known entry URL —
particularly POST-only endpoints, parameterised paths, and routes with no inbound links.
This causes ZAP to under-cover the attack surface on API-first targets like DVNA.

OWASP Noir is a static source-code analyser that extracts API endpoint definitions from
routes, controllers, and middleware, and emits the results as an OpenAPI 3.x (OAS3) JSON
document. ZAP natively supports OAS3 input via `-openapifile` / `-openapitargeturl`,
complementing `-quickurl` to expand the attack surface beyond what the spider discovers.

The problem was how to connect these two tools in the tally architecture without:
1. Adding inter-tool dependencies at the `ExecutionContext` level
2. Breaking existing ZAP quick-scan behaviour for repos that do not have Noir output
3. Coupling the scan execution order in the pipeline beyond what already exists

---

## Decision

**Noir runs as a standalone tool in the `web` scan segment before ZAP.** Its output is
a timestamped OAS3 JSON file written to `projects/<project>/tool_outputs/noir/`. Noir
findings are ingested as informational endpoint records (one row per endpoint) with
`skip = True` so they are never surfaced in the triage queue.

**ZAP discovers Noir output via filesystem probe at `build_execution_passes` time.**
A module-level helper `_find_noir_oas3(base_path, project_name, repo_name)` globs
`projects/<project>/tool_outputs/noir/<repo>_*_oas3.json` and returns the
lexicographically last match (which encodes the most recent timestamp in the filename).
If a match is found, `openapi_file` is added to the ZAP `ExecutionPass.kwargs`.
In OpenAPI mode the command becomes:
`zap.sh -cmd -openapifile <oas3> -openapitargeturl <url> -quickurl <url> -quickprogress -quickout <file>`
The `-quickurl` flag is required even in OpenAPI mode to trigger the spider and active
scan; without it ZAP imports the spec and exits without running or writing a report.
If no Noir output is found, ZAP falls back to the original `-quickurl`-only quick-scan mode.

**The OAS3 file is never deleted.** Unlike gitleaks (which deletes its temp file after
ingestion), the Noir output file must persist until ZAP consumes it. `parse_output` in
`NoirLocalTool` clears `_last_report_path` in a `finally` block but does not call
`unlink()`.

---

## Alternatives Considered

### Pass Noir output path through ExecutionContext
Add a `tool_artifacts` dict or similar to `ExecutionContext` so Noir can pass its OAS3
path directly to ZAP through a shared data structure.

**Rejected because**: `ExecutionContext` is a thin data carrier; adding cross-tool state
violates its single-responsibility. The filesystem is already the persistent store for
tool outputs; probing it is consistent with how the rest of the pipeline reads prior
results and requires no schema change.

### Emit ZAP as a post-processor of Noir at the pipeline level
Have the pipeline detect when Noir completes and conditionally modify ZAP's arguments
before it runs.

**Rejected because**: this requires the pipeline (`handlers.py`) to enumerate and
understand tool ordering dependencies — a fragile coupling that does not scale to
additional cross-tool dependencies.

### Use ZAP's REST API to import the OAS3 spec dynamically
Run ZAP in daemon mode and import the OAS3 spec via ZAP's HTTP API.

**Rejected because**: daemon mode requires a persistent ZAP instance and is substantially
more complex to orchestrate. The `-cmd` quick-scan mode is already in use and sufficient
for the current use case.

### Noir as a pre-processing hook rather than a registered tool
Allow Noir to run outside the normal tool lifecycle as a setup step.

**Rejected because**: registering Noir as a first-class tool means it participates in
availability checks, version logging, timeout handling, and result ingestion exactly like
every other tool — with no special cases in the scan orchestration layer.

---

## Pros

- ZAP scan coverage improves on API-centric repos: endpoints extracted statically by Noir
  are scanned even if they have no inbound crawler links.
- ZAP fallback is transparent: if Noir has not been run (or its output is stale or
  missing), ZAP silently reverts to `-quickurl` mode with no operator action required.
- Noir participates in the full tool lifecycle (availability checks, version logging,
  timeout, ingest) without special-casing in the pipeline.
- The filesystem handoff is decoupled: Noir and ZAP do not need to run in the same
  process invocation. A Noir run from a prior session will be picked up by ZAP in a
  subsequent session.

---

## Cons

- The OAS3 file is not cleaned up after ZAP consumes it. It persists in
  `tool_outputs/noir/` indefinitely, consuming disk space over many scan cycles.
- Timestamp-based discovery means a stale Noir run will be used if Noir is not re-run
  before ZAP. ZAP will scan endpoints from the previous run's spec without warning.
- The `-quickurl` flag is required even in OpenAPI mode to trigger the active scan.
  This is a ZAP implementation detail that is not obvious from the command syntax; if
  ZAP changes this behaviour in a future version, the passthrough will silently break.

---

## Consequences

### Positive
- Noir findings appear in SQLite as informational rows. They are excluded from triage
  (`skip = True`) but can be queried and counted. `count_findings` reports
  `summary.total_endpoints`.
- File retention is implicit: the OAS3 file persists in `tool_outputs/noir/` alongside
  other tool output files (ZAP reports, semgrep JSON), consistent with the project's
  data-retention approach.

### Negative
- A stale Noir OAS3 file from a previous scan will be picked up by ZAP unless Noir is
  explicitly re-run. The endpoint coverage may reflect an earlier version of the codebase.
- The `_find_noir_oas3` glob at `build_execution_passes` time introduces a filesystem
  read in the tool configuration path. On slow filesystems this adds latency before each
  ZAP pass.

### New Decisions Required
- ADR-0013 covers the segment-level organisation and the ZAP-without-Noir user-facing
  gate that were delivered alongside this work.
- A decision is needed on OAS3 file retention policy: whether old Noir outputs should
  be pruned after a configurable number of scans or a time window.

---

## Influences

- DVNA (Damn Vulnerable Node Application) as the primary test target, where ZAP's
  crawler-only mode missed POST endpoints and parameterised routes that Noir was able
  to discover statically.
- The existing filesystem-based tool output convention (`tool_outputs/<tool>/`) that
  provided a natural handoff mechanism without requiring a new inter-tool communication
  channel.

---

## Related Decisions

- [ADR-0013: Rename "api" Segment to "web" and Enforce Noir as a ZAP Prerequisite](./ADR-00013-rename-api-segment-to-web-and-enforce-noir-before-zap.md) — the segment-level organisation and user-facing gate that complement this decision
- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — Noir findings are ingested as SQLite rows via the standard pipeline

---

## Review Date

Review if ZAP's CLI interface changes such that `-quickurl` is no longer required in
OpenAPI mode, or if a dedicated inter-tool artifact registry is introduced that would
replace the filesystem-probe handoff pattern.
