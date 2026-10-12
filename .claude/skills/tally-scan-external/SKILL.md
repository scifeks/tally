---
name: tally-scan-external
description: >
  Run an external Claude Code security scan on the developer's local
  code and submit developer-ready findings back to Tally through
  MCP. Begins with scoping (SCOPING.md), runs multi-agent
  reconnaissance to produce structured attack-surface specs (OpenAPI
  3.1, AsyncAPI 3.0, hardware YAML), ingests specs via OAS3 MCP
  tool, dispatches domain family agents per code partition with auth
  phase awareness, sweeps dead code, runs optional adversarial
  verification, and submits every finding through Tally's ingest
  tools. Invoke when the user says "scan with tally", "run tally
  scan", "tally-scan-external", or asks to security-scan a repo
  with the Tally skill family.
---

# Tally external scan orchestrator

Runs a multi-phase security scan against the developer's local
code. Phase 1 establishes scope. Phase 2 dispatches parallel recon
mapper agents to build structured attack-surface specs. Phase 3
ingests the merged spec into Tally's URL inventory. Phase 4
dispatches domain family agents per code partition using partition
data extracted from the specs. Phase 5 sweeps dead code. Phase 6
optionally runs adversarial verification. Phase 7 submits all
findings to Tally through MCP and deduplicates.

The orchestrator never inspects the target code itself. It
dispatches subagents, reads their structured output, routes
findings to the MCP tools, and drives the lifecycle.

## Inputs

- **Project name** (required). The Tally project to scan. If not
  given, use `list_projects` and prompt the developer to pick.
- **Repo IDs** (optional). Which of the project's repos to scan.
  Default: every repo the project has.
- **Auth token** (required). The developer's MCP bearer token
  from their environment. Never log this value.

## MCP tools this skill calls

Every tool takes the auth_token as a named parameter and returns a
JSON dict.

| Tool | Purpose |
|---|---|
| `list_projects` | Enumerate accessible projects and their latest run_id. |
| `create_scan_run` | Open a new scan_run for the picked project. |
| `submit_finding` | Persist one finding under the run_id. |
| `get_duplicate_candidates` | Return candidate duplicate groups after all submits complete. |
| `resolve_duplicates` | Mark losers as duplicates of a picked survivor. |
| `end_scan` | Close the scan_run and set finished_at. |
| `ingest_attack_surface` | Populate URL inventory from a merged attack-surface spec. Takes `project`, `repo_name`, `spec_path`. Returns `{"status": "ok", "endpoints_ingested": int}`. |

The exact per-tool argument list is documented at
`mcp_server/server.py`. Every tool takes `auth_token` as a named
parameter.

## Steps

### Step 1: Scoping

Check for an existing `SCOPING.md` at
`projects/<name>/agentic/SCOPING.md` (the path under
`ProjectPaths.agentic_dir`).

- **If present:** ask the developer via `AskUserQuestion` whether
  to reuse the existing scope or redo it.
- **If absent or redoing:** if the project is already known (from
  step 2 of a previous run or the user's invocation), use it. If
  not, call `list_projects` and ask the developer to pick. Read
  `project.json` and repo configs to auto-populate
  draft fields:
  - Project name from `project.json`.
  - Local paths from repo configs.
  - Permitted targets from `RepoService.base_urls`.
  - Auth contexts from `RepoAuth`.
  - Languages from `RepoService.languages`.
  Then invoke the `writing-scopes` skill via the Skill tool with
  the pre-filled defaults. Skip Q5 (pinned state) and Q15
  (authorization). Write the final `SCOPING.md` to
  `projects/<name>/agentic/SCOPING.md`.

Create the `agentic/` directory with `mkdir -p` using the path
from `ProjectPaths.agentic_dir` before writing.

### Step 2: Pick the project and repos

Call `list_projects(auth_token=<token>)`. The response is a list
of `{project_id, project_name, path, latest_run_id}` entries.
Present the project names to the developer and ask which one to
scan. Use `AskUserQuestion`. Then ask which repos to include;
default to every repo the project has.

Record `project_name`, `project_id`, `repo_ids`, `repo_paths`,
and `latest_run_id` for later steps.

### Step 3: Continue-mode or new-mode

Ask the developer whether to continue an existing run or start a
new one. Use `AskUserQuestion` with two options:

- Continue previous run (uses `latest_run_id` from step 2).
- Start a new scan.

If the developer picks continue and `latest_run_id` is null, fall
back to new-mode and note the fallback to the developer.

For new-mode, call:

```
create_scan_run(
  project=<project_name>,
  project_id=<project_id>,
  repo_ids=<repo_ids>,
  auth_token=<token>,
)
```

Record the returned `run_id`. This `run_id` MUST be reused for
every submit, dedup, and end_scan call in this invocation.

### Step 4: Adversarial verification opt-in

Ask the developer: `Run adversarial verification pass?
(default: no)`. Use `AskUserQuestion` with two options:

- No, submit findings directly.
- Yes, run adversarial verification first.

Record the answer for step 8. Adversarial verification is off by
default; the developer opts in per invocation when they want extra
rigor.

### Step 5: Reconnaissance

#### 5a: Check for existing recon

Check for an existing merged spec at
`projects/<name>/agentic/recon/attack-surface.yaml`. If present,
ask the developer via `AskUserQuestion` whether to reuse it or
redo recon. If reusing, skip 5b through 5h and proceed to 5i
(ingest), then step 6.

#### 5b: Source tree survey

Run a bash survey of the source tree. Use `find` to count source
files and lines of code per directory. Do not read source file
contents at this stage.

```bash
find <repo_path> -type f \( -name '*.py' -o -name '*.php' \
  -o -name '*.js' -o -name '*.jsx' -o -name '*.ts' \
  -o -name '*.tsx' \) \
  | grep -v node_modules | grep -v vendor \
  | grep -v __pycache__ | wc -l
```

```bash
find <repo_path> -type f \( -name '*.py' -o -name '*.php' \
  -o -name '*.js' -o -name '*.jsx' -o -name '*.ts' \
  -o -name '*.tsx' \) \
  | grep -v node_modules | grep -v vendor \
  | grep -v __pycache__ | xargs wc -l 2>/dev/null | tail -1
```

Record per-directory file counts and LOC totals.

#### 5c: Split decision

One recon mapper agent per repo by default. Apply these overrides:

- **Subdivide** repos exceeding 200 source files or 30k LOC along
  top-level directories.
- **Group** repos under 20 source files into a single agent.
- Separate infrastructure code from application code.
- Read-only-for-tracing repos do not get their own agent.

#### 5d: Agent manifest

Build a text table of planned agents:

| Agent name | Repo | Directories | Estimated size | Tracing paths | Output description |

Present to the developer via `AskUserQuestion`. Wait for approval
before dispatching.

#### 5e: Dispatch recon mapper agents

Dispatch `tally-scan-recon-mapper` agents in parallel (agent
definition at `.claude/agents/tally-scan-recon-mapper.md`, model
`claude-opus-4-6[1m]`).

Each agent receives in its dispatch prompt:

- SCOPING.md content (from step 1).
- Assigned directories (from 5c).
- Tracing paths (directories the agent may read but does not map).
- Auth phase (from SCOPING.md auth contexts).
- Budget, computed per agent from 5b survey data:
  `20 + (files / 100) * 15 + (loc / 10000) * 10`, floor 30,
  ceiling 300.
- Output path:
  `projects/<name>/agentic/recon/partials/<agent-name>.partial.yaml`.
- Instruction to read `references/recon-prompt.md` for methodology
  and `references/attack-surface-schema.md` for the spec format.

The subagent's return message must be under 20 words; the partial
spec files are the output.

#### 5f: Collect partials

After all agents return, read each partial file. Validate that
each is valid YAML. Log any agent that produced empty or malformed
output.

#### 5g: Merge partials

Merge all valid partials into a single spec at
`projects/<name>/agentic/recon/attack-surface.yaml`. If agents
produced AsyncAPI or hardware partials, merge those into
`attack-surface-async.yaml` and `attack-surface-hardware.yaml`
respectively.

Duplicate endpoint resolution: when two partials contain the same
endpoint, keep the one with more parameters.

#### 5h: Completeness checklist

Run the five completeness checks against the merged spec:

1. **File coverage.** Every source file in 5b's survey appears in
   at least one partition's file list in the merged spec. Source
   files that do not appear in any partition are the **dead code
   list** (consumed by step 7). Flag any uncovered files.
2. **Endpoint exhaustiveness.** Run an independent `grep` for
   route decorators and URL patterns across all in-scope repos.
   Compare the count against the merged spec's total endpoint
   count. A discrepancy greater than 10% triggers a warning.
3. **Parameter completeness.** Every endpoint has at least one
   parameter documented, or an explicit
   `x-audit-no-params: true` annotation.
4. **Cross-boundary resolution.** Every
   `x-audit-cross-boundary` entry has a corresponding entry on
   the other side (another partition's spec), or is flagged as
   unresolved.
5. **Auth boundary coverage.** Every auth middleware or decorator
   found by `grep` in the codebase is referenced by at least one
   endpoint's `x-audit-auth-discovered`. Unreferenced auth
   checks suggest missed endpoints behind that auth.

Present results to the developer. Ask whether to proceed or
re-run specific components.

#### 5i: Ingest attack surface

Call the `ingest_attack_surface` MCP tool to populate the URL
inventory from the merged spec:

```
ingest_attack_surface(
  project=<project_name>,
  repo_name=<repo_name>,
  spec_path=<path to merged attack-surface.yaml>,
)
```

The tool returns `{"status": "ok", "endpoints_ingested": <int>}`.
Call once per repo if multiple repos produced separate merged
specs. Log the ingested endpoint count.

#### 5-fallback: Legacy mode

If all mapper agents fail (empty or malformed output from every
agent), skip recon entirely. Dispatch individual `tally-scan-*`
skills against the full repo without partition context. Do NOT
dispatch the retired `tally-scan-recon` agent.

Legacy mode replaces steps 5 through 7 with direct skill
dispatch (no partitions, no dead code sweep). The `tally-scan-*`
skills produce findings directly. Proceed to step 8
(adversarial) with those findings.

### Step 6: Dispatch domain agents per partition

Read `references/family-map.md` for the 10 domain family
definitions and their component skills.

Extract partition data from the merged YAML specs as structured
text, following the extraction format in
`references/attack-surface-schema.md` (Partition Data Extraction
section). Each partition becomes a `${PARTITION_DATA}` block for
the domain agent prompt.

For each partition in the merged spec:

1. Determine which languages are present in the partition's files
   (by file extension).
2. For each domain family in `family-map.md`:
   a. Check if the family's primary languages overlap with the
      partition's languages. Skip the family if no overlap.
   b. For the JWT family, additionally check if the partition's
      files import any JWT libraries (`jwt`, `jsonwebtoken`,
      `PyJWT`, `jose`, `firebase/php-jwt`). Skip if not.
   c. Build the subagent prompt from
      `references/domain-agent-prompt.md`, filling in:
      - `${FAMILY_NAME}`: the family name from family-map.md
      - `${PARTITION_ID}`: the partition label (SG-1, SG-2, etc.)
      - `${PARTITION_DATA}`: the structured text block extracted
        from the merged YAML for this partition
      - `${SKILL_FILE_LIST}`: paths to each component skill's
        SKILL.md (from family-map.md "Skill Directories" column)
      - `${LANGUAGE_REF_LIST}`: paths to per-language reference
        files (e.g., `tally-scan-injection-sql/references/python.md`)
        for languages present in the partition
   d. Include the auth-phase mapping instruction in the prompt:
      domain agents set `meta.auth_phase` per finding from each
      endpoint's `x-audit-trust-boundary` in the partition data.
      `unauth` maps to `unauthenticated`, `auth` to
      `authenticated`, `admin` to `admin`.
   e. Dispatch the subagent using agent type `tally-scan-domain`.

Dispatch agents in parallel. Each agent returns a JSON list of
findings.

For partitions from repos that exceeded the 5c split thresholds,
dispatch families sequentially (one at a time) to avoid context
overload. Still dispatch all relevant families.

#### Subagent failure handling

If a subagent crashes, returns malformed JSON, or produces no
output:

- Log the family name, partition ID, and the error (or "no
  output").
- Exclude it from the batch and continue with the remaining
  subagents' findings.
- Track the failure for the summary in step 11.

The scan is best-effort; a single domain agent failure should not
abort the whole run.

### Step 7: Dead code sweep

Build the dead code list from the file coverage check in step 5h:
source files that appear in the 5b survey but not in any
partition's file list in the merged spec. If the list is empty,
skip to step 8.

For each domain family in `family-map.md`:

1. Check if any dead code files match the family's primary
   languages. Skip the family if no match.
2. Build the subagent prompt from
   `references/dead-code-sweep-prompt.md`, filling in:
   - `${FAMILY_NAME}`: the family name
   - `${DEAD_CODE_INVENTORY}`: the dead code file list derived
     from the 5h file coverage check
   - `${SKILL_FILE_LIST}`: same as step 6
   - `${LANGUAGE_REF_LIST}`: same as step 6, filtered to
     languages present in the dead code files

Dispatch sweep agents in parallel using agent type
`tally-scan-domain` (same agent type as step 6; the dispatch
prompt differentiates the behavior). Each returns a JSON list
of findings (all with `confidence: potential` and
`finding_type: ["weakness"]`).

Collect sweep findings and merge them with the domain agent
findings from step 6.

### Step 8: Optional adversarial pass

Concatenate all findings from steps 6 and 7 into a single batch.

If step 4 was `no`: skip to step 9 with the raw batch.

If step 4 was `yes`:

- Check for `.claude/skills/tally-scan-adversarial/` on disk.
- If absent: report to the developer that the adversarial skill
  is not installed, and proceed to step 9 with the raw batch.
- If present: dispatch the `tally-scan-adversarial` skill on the
  batch. Its output is `{verified: [...], dropped: [...]}`.
  Proceed to step 9 with the `verified` list.

### Step 9: Submit each finding

For each finding in the (possibly filtered) batch, call:

```
submit_finding(
  project=<project_name>,
  project_id=<project_id>,
  repo_id=<repo_id_for_this_finding>,
  run_id=<run_id>,
  finding=<finding_payload>,
  auth_token=<token>,
)
```

The `finding_payload` must conform to `mcp-payload-shape.md`.
Domain agents set `meta.auth_phase` on each finding (see step
6.d). Verify each submitted finding has this field populated.
Track accepted and rejected counts by `rule_id`.

On per-finding rejection, log the returned error string and
continue. Do NOT retry the payload verbatim; the validator is
deterministic. If a family's payloads systematically fail, that
is a prompt bug to report.

Never log:

- The `auth_token` value.
- The raw finding payload beyond `finding_id` and `status`. Code
  snippets in finding bodies may themselves contain secrets.

### Step 10: Required dedup pass

Call `get_duplicate_candidates(project=<project_name>,
run_id=<run_id>, auth_token=<token>)`. The response is
`{"groups": [[<finding_id>, ...], ...]}`.

If the groups list is empty, proceed to step 11.

For each group:

- Fetch each finding's fields you need to reason about the
  survivor. If the finding data is not in your context from
  step 9's accepted responses, do not skip; err on the side of
  keeping every group's data explicit.
- Pick the survivor by these criteria, in order:
  1. Tightest `line_number` (closest to the true sink).
  2. Fullest `description` and `meta.remediation`.
  3. Highest `severity` (`critical` beats `high`).
  4. `confirmed` beats `probable` beats `potential`.
- Call:

  ```
  resolve_duplicates(
    project=<project_name>,
    run_id=<run_id>,
    survivor_id=<picked_id>,
    removed_ids=[<the other IDs in the group>],
    auth_token=<token>,
  )
  ```

- On `{"status": "rejected", "error": "..."}`, log the error and
  continue with the next group. Rejection means the picked
  survivor is itself already a duplicate; pick another from the
  group.

This pass is required, not opt-in. Never skip it, even when every
group appears to be a single-element self-group.

### Step 11: Close the scan_run

Call:

```
end_scan(
  project=<project_name>,
  project_id=<project_id>,
  run_id=<run_id>,
  auth_token=<token>,
)
```

Keep recon partials in `recon/partials/` for reuse and audit
reference. Do not delete them.

Report to the developer:

- **Recon results:** number of recon mapper agents dispatched and
  how many succeeded. Number of entry points, inputs, partitions,
  and dead code files identified from the merged spec.
- **Completeness checklist results:** pass or fail status for each
  of the 5 checks from step 5h.
- **Domain agents:** number dispatched (by family and partition)
  and how many succeeded.
- **Dead code sweep:** number of sweep agents dispatched and how
  many succeeded.
- **Failures:** names of any agents that failed (with family,
  partition, and reason).
- **Finding counts:** total collected from domain agents vs. dead
  code sweep. Counts accepted, rejected, and marked as duplicate.
- **Auth phase breakdown:** number of findings per auth phase
  (`unauthenticated`, `authenticated`, `admin`).
- **Run ID** for downstream inspection.

## Constraints

- Reuse the same `run_id` for every submit, dedup, and end_scan
  call in this invocation. Never create a second run mid-flow.
- The dedup pass in step 10 is required. Never skip it.
- Never log the `auth_token` value. Never log a raw finding
  payload beyond `finding_id` and `status`. Source snippets in
  finding bodies may themselves contain secrets.
- Recon mapper agents MUST use model `claude-opus-4-6[1m]`. Do
  not use the session model for recon.
- Domain agents and sweep agents use the session's default model.
- Dispatch domain agents per partition, not per individual skill.
  Each domain agent loads all its family's component skills as
  reference material.

## References

- `references/mcp-payload-shape.md`: exact JSON payload every
  scanner subagent must return.
- `references/skill-template.md`: canonical scanner-skill
  template for individual `tally-scan-*` skills.
- `references/recon-prompt.md`: recon subagent prompt with
  attack surface mapping methodology.
- `references/attack-surface-schema.md`: structured spec format
  for OpenAPI 3.1, AsyncAPI 3.0, and hardware YAML with
  `x-audit-*` extensions and the 12 typed sink categories.
- `references/family-map.md`: maps domain families to their
  component `tally-scan-*` skills.
- `references/gate-rules.md`: classification gate definitions
  for domain agents.
- `references/domain-agent-prompt.md`: domain agent prompt
  template with partition scope and gating instructions.
- `references/dead-code-sweep-prompt.md`: dead code sweep
  agent prompt with pattern-based detection rules.

## Common scenarios

### No scanner skills installed

If step 6 finds no `tally-scan-*` directories matching any
family in `family-map.md`, report to the developer that no
scanner skills are installed and stop. Do not create a scan_run.

### `list_projects` returns empty

If step 2's `list_projects` returns no projects, report to the
developer that no accessible projects exist for this token and
stop.

### Auth token missing or invalid

Every MCP tool raises `PermissionError("Invalid or missing MCP
token")` on auth failure. On the first such error, report to the
developer that the token is invalid and stop. Do not retry with a
different token.

### Recon fails

If all recon mapper agents crash or produce empty/malformed
output, fall back to legacy mode (step 5-fallback): dispatch
individual `tally-scan-*` skills against the full repo without
partition context. Report the recon failure to the developer.
Legacy mode replaces steps 5 through 7 (see step 5-fallback).

### One domain agent fails

If one of the parallel domain agents crashes or returns malformed
output, log the failure and proceed with the successful agents'
findings. The scan is best-effort; a single agent failure should
not abort the whole run.

### Pure library (no entry points)

If the merged spec has no entry points (empty `paths`), the
entire codebase is treated as dead code. Skip step 6 (no
partitions to scan). Step 7 sweeps every source file as dead
code. Findings will all be `finding_type: ["weakness"]` with
`confidence: potential`.
