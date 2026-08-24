---
name: tally-scan-external
description: >
  Run an external Claude Code security scan on the developer's local
  code and submit developer-ready findings back to Tally through
  MCP. Runs a reconnaissance phase to map the attack surface, then
  dispatches domain family agents per code partition, sweeps dead
  code, runs optional adversarial verification, and submits every
  finding through Tally's ingest tools. Invoke when the user says
  "scan with tally", "run tally scan", "tally-scan-external", or
  asks to security-scan a repo with the Tally skill family.
---

# Tally external scan orchestrator

Runs a multi-phase security scan against the developer's local
code. Phase 1 (recon) maps entry points, inputs, call graph, trust
boundaries, and dead code. Phase 2 dispatches domain family agents
per code partition with recon context. Phase 3 sweeps dead code.
Phase 4 optionally runs adversarial verification. Phase 5 submits
all findings to Tally through MCP and deduplicates.

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

The exact per-tool argument list is documented at
`mcp_server/server.py`. Every tool takes `auth_token` as a named
parameter.

## Steps

### Step 1: Pick the project and repos

Call `list_projects(auth_token=<token>)`. The response is a list
of `{project_id, project_name, path, latest_run_id}` entries.
Present the project names to the developer and ask which one to
scan. Use `AskUserQuestion`. Then ask which repos to include;
default to every repo the project has.

Record `project_name`, `project_id`, `repo_ids`, `repo_paths`,
and `latest_run_id` for later steps.

### Step 2: Continue-mode or new-mode

Ask the developer whether to continue an existing run or start a
new one. Use `AskUserQuestion` with two options:

- Continue previous run (uses `latest_run_id` from step 1).
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

### Step 3: Adversarial verification opt-in

Ask the developer: `Run adversarial verification pass?
(default: no)`. Use `AskUserQuestion` with two options:

- No, submit findings directly.
- Yes, run adversarial verification first.

Record the answer for step 7. Adversarial verification is off by
default; the developer opts in per invocation when they want extra
rigor.

### Step 4: Reconnaissance

Dispatch a recon subagent using agent type `tally-scan-recon`
(defined in `.claude/agents/tally-scan-recon.md`, which pins
the model to `claude-sonnet-4-6`).

The subagent's dispatch prompt must include:

- The target repo paths to scan. These are the directories
  containing the code the user wants scanned. If the user is
  running Claude Code from within the target project, the repo
  path is the current working directory. If the Tally project
  registry returns paths for the selected repos, use those.
  When in doubt, use the cwd.
- The path to write the manifest file (use
  `<repo_path>/.tally-recon-manifest.md`).
- An instruction to read `references/recon-prompt.md` for the
  full methodology.

The subagent's return message must be under 20 words; the
manifest file IS the output.

After the subagent returns, read the manifest file. It contains:

1. **Codebase Profile**: languages, frameworks, package managers
2. **Input Inventory**: numbered table of user-controlled inputs
3. **Trust Boundary Map**: auth boundaries, external calls
4. **Application Call Graph**: entry points to sinks
5. **Shared Infrastructure**: modules used by >50% of endpoints
6. **Scope Partitions**: SG-N groups with files and inputs
7. **Dead Code Inventory**: unreachable files with sink flags

If the manifest is empty or malformed, report to the developer
that recon failed and fall back to legacy mode (step 4b).

#### Step 4b: Legacy fallback

If recon fails, fall back to the original dispatch mode:
enumerate every `tally-scan-*` skill directory and dispatch one
subagent per skill against the full repo, without recon context.
This is the pre-partition behavior. Skip steps 5 and 6; proceed
to step 7 with the collected findings.

### Step 5: Dispatch domain agents per partition

Read `references/family-map.md` for the 10 domain family
definitions and their component skills.

For each partition in the recon manifest:

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
      - `${PARTITION_DATA}`: the partition's section from the
        recon manifest (inputs, entry points, files, shared
        infrastructure, trust boundaries)
      - `${SKILL_FILE_LIST}`: paths to each component skill's
        SKILL.md (from family-map.md "Skill Directories" column)
      - `${LANGUAGE_REF_LIST}`: paths to per-language reference
        files (e.g., `tally-scan-injection-sql/references/python.md`)
        for languages present in the partition
   d. Dispatch the subagent using agent type `tally-scan-domain`.

Dispatch agents in parallel. Each agent returns a JSON list of
findings.

For partitions marked `SEQUENTIAL-FALLBACK` in the recon manifest,
dispatch families sequentially (one at a time) to avoid context
overload. Still dispatch all relevant families.

#### Subagent failure handling

If a subagent crashes, returns malformed JSON, or produces no
output:

- Log the family name, partition ID, and the error (or "no
  output").
- Exclude it from the batch and continue with the remaining
  subagents' findings.
- Track the failure for the summary in step 10.

The scan is best-effort; a single domain agent failure should not
abort the whole run.

### Step 6: Dead code sweep

Read the dead code inventory section from the recon manifest. If
the inventory is empty, skip to step 7.

For each domain family in `family-map.md`:

1. Check if any dead code files match the family's primary
   languages. Skip the family if no match.
2. Build the subagent prompt from
   `references/dead-code-sweep-prompt.md`, filling in:
   - `${FAMILY_NAME}`: the family name
   - `${DEAD_CODE_INVENTORY}`: the dead code inventory table
     from the recon manifest
   - `${SKILL_FILE_LIST}`: same as step 5
   - `${LANGUAGE_REF_LIST}`: same as step 5, filtered to
     languages present in the dead code files

Dispatch sweep agents in parallel using agent type
`tally-scan-domain` (same agent type as step 5; the dispatch
prompt differentiates the behavior). Each returns a JSON list
of findings (all with `confidence: potential` and
`finding_type: ["weakness"]`).

Collect sweep findings and merge them with the domain agent
findings from step 5.

### Step 7: Optional adversarial pass

Concatenate all findings from steps 5 and 6 into a single batch.

If step 3 was `no`: skip to step 8 with the raw batch.

If step 3 was `yes`:

- Check for `.claude/skills/tally-scan-adversarial/` on disk.
- If absent: report to the developer that the adversarial skill
  is not installed, and proceed to step 8 with the raw batch.
- If present: dispatch the `tally-scan-adversarial` skill on the
  batch. Its output is `{verified: [...], dropped: [...]}`.
  Proceed to step 8 with the `verified` list.

### Step 8: Submit each finding

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
Track accepted and rejected counts by `rule_id`.

On per-finding rejection, log the returned error string and
continue. Do NOT retry the payload verbatim; the validator is
deterministic. If a family's payloads systematically fail, that
is a prompt bug to report.

Never log:

- The `auth_token` value.
- The raw finding payload beyond `finding_id` and `status`. Code
  snippets in finding bodies may themselves contain secrets.

### Step 9: Required dedup pass

Call `get_duplicate_candidates(project=<project_name>,
run_id=<run_id>, auth_token=<token>)`. The response is
`{"groups": [[<finding_id>, ...], ...]}`.

If the groups list is empty, proceed to step 10.

For each group:

- Fetch each finding's fields you need to reason about the
  survivor. If the finding data is not in your context from
  step 8's accepted responses, do not skip; err on the side of
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

### Step 10: Close the scan_run

Call:

```
end_scan(
  project=<project_name>,
  project_id=<project_id>,
  run_id=<run_id>,
  auth_token=<token>,
)
```

Clean up the recon manifest file if one was written.

Report to the developer:

- Recon results: number of entry points, inputs, partitions,
  and dead code files identified.
- Number of domain agents dispatched (by family and partition)
  and how many succeeded.
- Number of dead code sweep agents dispatched and how many
  succeeded.
- Names of any agents that failed (with family, partition, and
  reason).
- Number of findings collected: from domain agents vs. dead
  code sweep.
- Number accepted, rejected, and marked as duplicates.
- Run ID for downstream inspection.

## Constraints

- Reuse the same `run_id` for every submit, dedup, and end_scan
  call in this invocation. Never create a second run mid-flow.
- The dedup pass in step 9 is required. Never skip it.
- Never log the `auth_token` value. Never log a raw finding
  payload beyond `finding_id` and `status`. Source snippets in
  finding bodies may themselves contain secrets.
- The recon subagent MUST use model `claude-sonnet-4-6`. Do not
  use the session model for recon.
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

If step 5 finds no `tally-scan-*` directories matching any
family in `family-map.md`, report to the developer that no
scanner skills are installed and stop. Do not create a scan_run.

### `list_projects` returns empty

If step 1's `list_projects` returns no projects, report to the
developer that no accessible projects exist for this token and
stop.

### Auth token missing or invalid

Every MCP tool raises `PermissionError("Invalid or missing MCP
token")` on auth failure. On the first such error, report to the
developer that the token is invalid and stop. Do not retry with a
different token.

### Recon fails

If the recon subagent crashes or produces an empty/malformed
manifest, fall back to legacy mode (step 4b): dispatch individual
`tally-scan-*` skills against the full repo without recon context.
Report the recon failure to the developer. Skip steps 5 and 6.

### One domain agent fails

If one of the parallel domain agents crashes or returns malformed
output, log the failure and proceed with the successful agents'
findings. The scan is best-effort; a single agent failure should
not abort the whole run.

### Pure library (no entry points)

If recon reports no entry points, the entire codebase is treated
as dead code. Skip step 5 (no partitions to scan). Step 6 sweeps
every source file as dead code. Findings will all be
`finding_type: ["weakness"]` with `confidence: potential`.
