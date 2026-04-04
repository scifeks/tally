# ADR-0013: Rename the "api" Scan Segment to "web" and Enforce Noir as a ZAP Prerequisite

## Status
Accepted

## Date
2026-04-03

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

Both Noir (endpoint-discovery) and ZAP (DAST scanner) were previously assigned to the
`"api"` scan segment. This created three problems:

**Naming mismatch.** The `"api"` label implied the segment was narrowly about API testing.
In practice it covers the full web attack surface: endpoint discovery from source code,
spider-based crawling, and active vulnerability scanning. The segment name was misleading
to anyone reading the configuration or the codebase.

**No ordering guarantee.** Noir generates an OAS3 spec that ZAP consumes. Nothing in
the pipeline enforced that Noir ran before ZAP. If tools within a segment were iterated
in non-alphabetical order, or if a user requested ZAP without Noir, ZAP would silently
fall back to crawler-only mode and the analyst would not know why scan coverage was
reduced.

**No user-facing warning.** When a user requested a ZAP scan and Noir was absent from
the tool list and no OAS3 file already existed on disk, the system gave no indication
that endpoint-guided scanning was unavailable. The silent fallback was not visible.

ADR-012 established Noir as a registered tool that writes an OAS3 file to
`projects/<project>/tool_outputs/noir/`, and ZAP's filesystem probe to pick it up at
`build_execution_passes` time. This ADR covers the segment-level reorganisation and the
prerequisite gate that were delivered alongside that work.

---

## Decision

Rename the `"api"` segment to `"web"` across `SEGMENT_ORDER`, `BaseNoirTool`, and
`BaseZapTool`. Establish Noir as a declared prerequisite for ZAP by relying on
alphabetical sort order within the segment ("noir" < "zap") and by adding an explicit
user-facing warning when ZAP is requested without Noir and without an existing OAS3 file.

In practice this means:

1. `SEGMENT_ORDER` becomes `["sast", "sca", "secrets", "web"]`.
2. `BaseNoirTool.scan_segment = "web"` and `BaseZapTool.scan_segment = "web"`.
3. `ordered_repo_tools` sorts tool names alphabetically within each segment — no
   additional ordering logic is required; "noir" naturally precedes "zap".
4. `NoirHandler` is classified as `domain = "code"` (analyses source), `segment = "web"`
   (discovers web endpoints). `ZapHandler` is classified as `domain = "web"`.
5. `IngestHandler`: code-domain / web-segment tools (Noir) bypass `filter_code_rows`
   because Noir produces URL findings, not file-path findings. `repo` is set from
   `event.repo` directly rather than derived from a `file_path` column.
6. `NoirHandler.should_enrich = False` — LLM enrichment adds no value to raw endpoint
   metadata (method + URL is self-describing).
7. When ZAP is requested and Noir is absent from the tool list and no OAS3 file exists
   on disk, the user is prompted with three options: (1) prepend Noir automatically
   (default), (2) run ZAP as a crawler-only quick scan, (3) cancel.
8. The web UI excludes Noir findings from the main findings table; they appear only in
   a dedicated "Discovered Attack Surface" report section.
9. The report generator adds a "Discovered Attack Surface" section showing Method, URI,
   Source File, and Parameters columns, labelled as informational — not vulnerability
   findings.

---

## Alternatives Considered

### Keep the "api" segment name
Leave `SEGMENT_ORDER` and both base wrappers unchanged; document the scope of the
segment separately.

**Rejected because**: the name is a first-class identifier visible in configuration
files, log output, and scan summaries. A misleading name causes ongoing confusion for
anyone reading the code or output. Renaming is a one-line change with no runtime cost.

### Explicit ordering list for "noir before zap"
Add a `TOOL_ORDER` list or a `depends_on` field to the tool interface so the scheduler
can enforce Noir → ZAP ordering independently of alphabetical position.

**Rejected because**: alphabetical sort achieves the same result without extra
indirection. "noir" < "zap" is stable, obvious, and requires no additional data
structure. The explicit-ordering mechanism would be justified if two tools in the same
segment were not in the desired alphabetical order — that is not the case here.

### Always auto-run Noir before ZAP
Remove the user prompt entirely and always prepend Noir to any ZAP request.

**Rejected because**: users may legitimately want a ZAP-only quick scan when an OAS3
spec already exists from a prior Noir run, or when Noir is unavailable in the
environment. Forced auto-prepend would add scan time without user consent. The three-
option prompt preserves user control while making the coverage tradeoff explicit.

### Enrich Noir findings with the LLM
Run endpoint metadata through the enrichment pipeline to classify or annotate endpoints.

**Rejected because**: a Noir row contains a method, a URI, an optional source file path,
and optional parameter names. There is no ambiguity for the LLM to resolve and no
severity classification to assign. Enrichment calls would consume tokens and add latency
for zero analyst value.

---

## Pros

- The segment name now matches its actual scope — full web attack surface discovery, not
  just API testing — making configuration and log output self-documenting.
- Alphabetical ordering within the segment provides a zero-overhead, dependency-free
  guarantee that Noir precedes ZAP in every scan that includes both tools.
- The ZAP-without-Noir prompt surfaces a coverage tradeoff that was previously invisible
  to users, without removing the option to skip Noir when appropriate.
- Separating Noir findings into a dedicated "Discovered Attack Surface" section in the
  report prevents informational endpoint records from polluting the vulnerability triage
  queue.

---

## Cons

- Any external tooling, scripts, or documentation that references the `"api"` segment
  name by string will silently break or produce no results after the rename.
- The alphabetical ordering guarantee is implicit — it is not enforced by a type system
  or explicit assertion. A future tool whose name sorts before "noir" (e.g. a hypothetical
  "attack-surface-mapper") would need to be placed in a different segment or the ordering
  assumption would need to be revisited.
- The ZAP-without-Noir prompt introduces an interactive gate into what was previously a
  fully non-interactive scan startup sequence. Automated pipelines that invoke tally
  headlessly must now account for this prompt or always include Noir in their tool list.

---

## Consequences

### Positive
- Scan execution order is correct by construction for all users who include both Noir
  and ZAP: Noir always runs first, its OAS3 output is on disk before ZAP's
  `build_execution_passes` is called.
- Analysts viewing the report see a clean separation between "endpoints discovered"
  (informational, from Noir) and "vulnerabilities found" (actionable, from ZAP and
  other tools).
- The `"web"` segment name is extensible: additional web-facing tools (e.g. a future
  JavaScript parser or a Wappalyzer-style fingerprinter) have a correct home without
  requiring another segment rename.

### Negative
- Existing scans or reports referencing segment `"api"` in stored metadata will not
  automatically migrate. Any query or filter keyed on segment name will need updating.
- The IngestHandler bypass for code-domain / web-segment tools is a special case in the
  ingest path. Future tools with the same domain/segment classification must be verified
  to not require `file_path`, or the bypass condition will need to be made more precise.

### New Decisions Required
- If a future tool sorts alphabetically before "noir" but must run after it within the
  "web" segment, an explicit ordering mechanism will need to be introduced. The
  alphabetical assumption should be documented as a constraint on tool naming for the
  "web" segment.
- A decision is needed on how automated / headless invocations of tally should signal
  their preferred ZAP-without-Noir behaviour (e.g. a `--no-interactive` flag that
  selects a default option).

---

## Influences

- **ADR-012** (Noir as pre-DAST step with OAS3 passthrough to ZAP): this ADR completes
  the organisational side of that work — ADR-012 established the file-based handoff
  mechanism; this ADR establishes the segment structure and user-facing gate that make
  the ordering and coverage tradeoff visible.
- The `filter_code_rows` bypass for Noir is a direct consequence of ADR-012's decision
  to model Noir findings as URL records rather than file-path records. That domain
  modelling decision forced a special case in the ingest path that this ADR formalises.

---

## Related Decisions

- Future ADR needed: headless / non-interactive invocation mode for tally (handles the ZAP-without-Noir prompt in CI/CD contexts)
- Future ADR needed: explicit tool ordering mechanism within a segment (if alphabetical sort becomes insufficient)

---

## Review Date

Review if a tool is added to the "web" segment whose name sorts before "noir", or if
tally gains a headless/CI invocation mode that requires a non-interactive answer to the
ZAP-without-Noir prompt.
