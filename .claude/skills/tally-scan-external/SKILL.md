---
name: tally-scan-external
description: >
  Run an external Claude Code security scan on the developer's local
  code and submit developer-ready findings back to Tally through
  MCP. Dispatches per-vulnerability-category scanner subagents in
  parallel, collects findings, runs a required dedup pass, and
  submits every finding through Tally's ingest tools. Invoke when
  the user says "scan with tally", "run tally scan",
  "tally-scan-external", or asks to security-scan a repo with the
  Tally skill family.
---

# Tally external scan orchestrator

Dispatches every installed scanner skill in parallel against the
developer's local code, submits the collected findings to Tally
through MCP, and closes the scan_run cleanly. Optionally runs an
adversarial verification pass on the collected batch before
submission.

Every scanner subagent uses its own `tally-scan-<leaf>` skill
(one skill per vulnerability category per D16). The orchestrator
never inspects the target code itself; it wires the subagents,
routes their JSON output to the MCP tools, and drives the
lifecycle.

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

Record `project_name`, `project_id`, `repo_ids`, and
`latest_run_id` for later steps.

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

Record the answer for step 5. Per D11, adversarial verification is
off by default; the developer opts in per invocation when they
want extra rigor.

### Step 4: Dispatch scanner subagents in parallel

Enumerate every directory under `.claude/skills/` matching
`tally-scan-*`, excluding `tally-scan-external` (this skill) and
`tally-scan-adversarial` (the verifier from Slice 4).

For each remaining scanner skill, dispatch one subagent in
parallel per the parallel-dispatch pattern in
`~/.claude/plugins/cache/superpowers-marketplace/superpowers/5.0.7/skills/dispatching-parallel-agents/SKILL.md`.

Each subagent prompt includes:

- The scanner skill's `SKILL.md` as its instruction source.
- The target repo paths (from step 1's `list_projects` response).
- The required output shape:
  `references/mcp-payload-shape.md`.
- Explicit instruction: return a JSON list of findings, nothing
  else.

Wait for every subagent to return. Do not proceed to step 5 until
every subagent has produced its output.

### Step 5: Optional adversarial pass

Concatenate every subagent's finding list into a single batch.

If step 3 was `no`: skip to step 6 with the raw batch.

If step 3 was `yes`:

- Check for `.claude/skills/tally-scan-adversarial/` on disk.
- If absent: report to the developer that the adversarial skill
  is not installed, and proceed to step 6 with the raw batch.
- If present: dispatch the `tally-scan-adversarial` skill on the
  batch. Its output is `{verified: [...], dropped: [...]}`.
  Proceed to step 6 with the `verified` list.

### Step 6: Submit each finding

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
deterministic. If a scanner's payloads systematically fail, that
is a scanner bug to report.

Never log:

- The `auth_token` value.
- The raw finding payload beyond `finding_id` and `status`. Code
  snippets in finding bodies may themselves contain secrets.

### Step 7: Required dedup pass

Call `get_duplicate_candidates(project=<project_name>,
run_id=<run_id>, auth_token=<token>)`. The response is
`{"groups": [[<finding_id>, ...], ...]}`.

If the groups list is empty, proceed to step 8.

For each group:

- Fetch each finding's fields you need to reason about the
  survivor. If the finding data is not in your context from
  step 6's accepted responses, do not skip; err on the side of
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

Per D23, this pass is required, not opt-in. Never skip it, even
when every group appears to be a single-element self-group.

### Step 8: Close the scan_run

Call:

```
end_scan(
  project=<project_name>,
  project_id=<project_id>,
  run_id=<run_id>,
  auth_token=<token>,
)
```

Report to the developer:

- Number of scanner skills dispatched.
- Number of findings collected.
- Number accepted, rejected, and marked as duplicates.
- Run ID for downstream inspection.

## Constraints

- Reuse the same `run_id` for every submit, dedup, and end_scan
  call in this invocation. Never create a second run mid-flow.
- The dedup pass in step 7 is required per D23. Never skip it.
- Never log the `auth_token` value. Never log a raw finding
  payload beyond `finding_id` and `status`. Source snippets in
  finding bodies may themselves contain secrets.
- Every subagent uses its own `tally-scan-<leaf>` skill. Do not
  ask a subagent to cover two vulnerability categories in one
  invocation.

## References

- `references/mcp-payload-shape.md`: exact JSON payload every
  scanner subagent must return.
- `references/skill-template.md`: canonical scanner-skill
  template. Slices 5-11 copy this for each new scanner skill.

## Common scenarios

### No scanner skills installed

If step 4 finds no `tally-scan-*` directories other than this
skill and (optionally) `tally-scan-adversarial`, report to the
developer that no scanner skills are installed and stop. Do not
create a scan_run.

### `list_projects` returns empty

If step 1's `list_projects` returns no projects, report to the
developer that no accessible projects exist for this token and
stop.

### Auth token missing or invalid

Every MCP tool raises `PermissionError("Invalid or missing MCP
token")` on auth failure. On the first such error, report to the
developer that the token is invalid and stop. Do not retry with a
different token.

### One scanner subagent fails

If one of the parallel scanner subagents crashes or returns
malformed output, log the failure and proceed with the successful
subagents' findings. The scan is best-effort; a single scanner
failure should not abort the whole run.
