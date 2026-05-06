# MCP Triage System

## Overview

Tally's `triage` workflow is an automated finding-review pipeline built on the
Tally MCP server. After you run scans and ingest findings into a project's
SQLite database, `triage` launches the configured triage backend as a
subprocess, connects it to Tally's MCP tools, and has it read and update every
untriaged finding without requiring manual interaction.

The command model is backend-agnostic from the operator's perspective:

- `triage` runs the full batch workflow
- `triage --batch` computes and claims batches without launching a backend
- `triage --dry-run` computes batches and renders prompts without launching a
  backend

Backend selection is controlled by `triage_agent_provider` in
`config/global.json`:

- `""` or omission disables triage
- `"claude_code"` enables Claude Code-backed triage
- `"open_code"` enables OpenCode-backed triage

Provider-specific setup and runtime details live in separate docs:

- [Claude Code Triage Backend](./mcp-claude-code.md)
- [OpenCode Triage Backend](./mcp-opencode.md)

---

## Prerequisites

### Global config

`config/global.json` must contain a valid `triage_agent_provider` value. If the
key is omitted or set to `""`, triage commands fail immediately with a disabled
triage error.

### Python dependencies

Tally's install script installs the required Python packages, including the MCP
stack used by automated triage:

```bash
bash install.sh
```

If you need to install only the MCP dependency manually:

```bash
.venv/bin/pip install mcp
```

### A project with completed scans

The `triage` command queries `findings WHERE triaged_at IS NULL`. If the active
project has no findings in its SQLite database, triage exits immediately with
zero sessions run.

Run at least one scan and ingest its output before triaging:

```text
scan --tool=semgrep
```

### Backend runtime

The configured backend runtime must be installed and usable on the local
machine:

- Claude Code: see [Claude Code Triage Backend](./mcp-claude-code.md)
- OpenCode: see [OpenCode Triage Backend](./mcp-opencode.md)

---

## Configuration

These triage settings live in `config/global.json`.

### `triage_agent_provider`

**Default:** `""`

Selects the triage backend:

- `""` or omission disables triage
- `"claude_code"` enables the Claude Code backend
- `"open_code"` enables the OpenCode backend

### `mcp_batch_size`

**Default:** `10`
**Constraint:** must be >= 1

Controls the maximum number of findings returned by a single
`get_findings_batch` call. The MCP tool enforces this ceiling regardless of
what the backend requests.

Increase this if you want fewer sessions per run. Decrease it if large batches
are timing out before the backend finishes processing them.

### `mcp_batch_timeout_seconds`

**Default:** `30`
**Constraint:** must be >= 1

The number of seconds `get_findings_batch` will wait for the SQLite query to
return before giving up. On timeout the tool writes a failed audit row and
returns an empty list.

### `mcp_session_timeout_seconds`

**Default:** `300`

The number of seconds Tally will wait for a single backend subprocess to finish
before killing it and recording the session as failed.

Increase this if large batches are timing out. Decrease it if you want faster
failure detection.

---

## Running Triage

From inside the Tally REPL with an active project:

```text
triage
```

It uses the active project set with `project switch <name>`.

| Flag | Description |
|---|---|
| `--batch` | Run the batching phase only. No backend sessions are launched. |
| `--dry-run` | Batch and render prompts to the DEBUG log only. No backend or MCP session is launched. |

### What happens step by step

1. Tally resolves the active project and finds all rows where `triaged_at IS NULL`.
2. Findings are grouped into triage strategies based on the scanner that produced them.
3. Tally prepares a backend-owned session environment for the configured provider.
4. Tally launches one backend session per claimed strategy batch.
5. The backend calls Tally MCP tools to read findings and write triage updates.
6. After the subprocess exits, Tally checks `tool_audit_log` for update-tool
   calls made after the session started.
7. If at least one update call happened, the batch is marked `success`. If the
   process succeeded but made no update calls, the batch is marked
   `incomplete`. If the process failed or timed out, the batch is marked
   `failed`.
8. Backend-owned temporary session material is cleaned up automatically.

### Session result output

The REPL prints a one-line summary when triage finishes:

```text
Triage: 2 sessions run, 2 success, 0 failed, 0 incomplete
```

- `sessions_run`: number of strategy batches launched
- `success`: batches where at least one finding was updated
- `failed`: batches that timed out or where the backend exited non-zero
- `incomplete`: batches where the backend exited zero but made no update calls

### Verifying results

Check how many findings were triaged:

```bash
sqlite3 projects/<name>/sqlite/findings.db \
  "SELECT COUNT(*) FROM findings WHERE triaged_at IS NOT NULL"
```

---

## Understanding Triage Output

When the backend calls `update_finding` or `update_findings_batch`, Tally writes
a `triage` key into the finding's `meta` JSON column. The structure is:

```json
{
  "triage": {
    "confidence": "probable",
    "previous_confidence": "potential",
    "reasoning": "Traced user-controlled input from request.GET['q'] to the raw SQL query at db.execute(). No parameterisation or escaping is present.",
    "remediation": "Replace the raw string interpolation with a parameterised query using cursor.execute(sql, (value,)).",
    "attack_vector": "GET /search?q=<payload>",
    "call_stack": [
      "views/search.py:42 search_view",
      "db/queries.py:17 run_query"
    ],
    "triaged_by": "opencode",
    "triaged_at": "2026-05-06T14:23:01.456789+00:00",
    "strategy": "code_trace"
  }
}
```

### Field reference

**`confidence`**
The backend's assessment of whether the finding is a real vulnerability. Valid
values:

- `confirmed`
- `probable`
- `potential`
- `false_positive`

**`previous_confidence`**
The confidence value the finding had before triage.

**`reasoning`**
The backend's explanation of what it read, what it found, and why it assigned
the selected confidence.

**`remediation`**
Specific, actionable fix guidance.

**`attack_vector`**
The exposed request path, dependency attack surface, or access path involved in
the issue. `null` when not applicable.

**`call_stack`**
For `code_trace` confirmed findings, a list of `"file:line function"` strings
from entry point to sink. `null` for other strategies or unconfirmed findings.

**`triaged_by`**
Backend-owned marker for automated triage sessions:

- `"claudecode"` for Claude Code
- `"opencode"` for OpenCode

**`triaged_at`**
ISO 8601 UTC timestamp of when the update tool was called.

**`strategy`**
The triage strategy used for the finding: `code_trace`, `api_trace`,
`dependency`, or `enrich_only`.

> `requires_human_review` appears in some planning notes but is not implemented
> in the current codebase.

---

## Querying Triage Results

All queries below run against `projects/<name>/sqlite/findings.db`.

Open the database with:

```bash
sqlite3 projects/<name>/sqlite/findings.db
```

### All findings triaged recently

```sql
SELECT id, tool, severity, confidence, triaged_at, triaged_by
FROM findings
WHERE triaged_at IS NOT NULL
ORDER BY triaged_at DESC
LIMIT 50;
```

### All confirmed vulnerabilities

```sql
SELECT id, tool, file, severity, triaged_at, triaged_by
FROM findings
WHERE confidence = 'confirmed'
  AND triaged_at IS NOT NULL
ORDER BY severity, tool;
```

### All false positives

```sql
SELECT id, tool, file, severity, triaged_by
FROM findings
WHERE confidence = 'false_positive'
ORDER BY tool, file;
```

### Findings where confidence changed during triage

```sql
SELECT id, tool, confidence,
       json_extract(meta, '$.triage.previous_confidence') AS previous_confidence
FROM findings
WHERE triaged_at IS NOT NULL
  AND json_extract(meta, '$.triage.previous_confidence') != confidence
ORDER BY id;
```

---

## Troubleshooting

### Triage command says triage is disabled

**Cause:** `triage_agent_provider` is omitted or set to `""`.

**Fix:** Set `triage_agent_provider` to `"claude_code"` or `"open_code"` in
`config/global.json`, then make sure that backend's runtime is installed.

### Backend runtime is missing

**Symptom:** The REPL or web readiness surface reports the configured backend is
not installed.

**Fix:** Install and verify the selected runtime:

- Claude Code: see [Claude Code Triage Backend](./mcp-claude-code.md)
- OpenCode: see [OpenCode Triage Backend](./mcp-opencode.md)

### Session completes but no findings are updated

**Symptom:** The run summary shows one or more `incomplete` sessions. The
`tool_audit_log` contains read calls but no `update_finding` or
`update_findings_batch` calls.

**Cause:** The backend exited without making an update call. This can happen if
the prompt was not understood, `get_findings_batch` returned no findings, or
the backend hit a provider-specific issue before writing updates.

**Diagnosis:** Check the recent audit log:

```sql
SELECT tool_name, success, error, called_at
FROM tool_audit_log
ORDER BY called_at DESC
LIMIT 20;
```

If the failure mode looks backend-specific, continue with the provider doc:

- [Claude Code Triage Backend](./mcp-claude-code.md)
- [OpenCode Triage Backend](./mcp-opencode.md)

### Batch never fills and `get_findings_batch` returns empty

**Cause:** The SQLite query exceeded `mcp_batch_timeout_seconds`.

**Fix:** Increase the timeout in `config/global.json`:

```json
{
  "mcp_batch_timeout_seconds": 60
}
```

### Invalid field values rejected by `update_finding`

**Symptom:** `tool_audit_log` shows failed update calls with validation errors.

**Cause:** The backend submitted a value outside the allowed set. Valid values
include:

- `confidence`: `confirmed`, `probable`, `potential`, `false_positive`
- `severity`: `critical`, `high`, `medium`, `low`, `informational`
- `finding_type`: `secret`, `vulnerability`, `weakness`, `misconfiguration`,
  `exposure`, `dependency`, `informational`

Retrying the session may succeed. If it recurs consistently, the prompt
template for the affected strategy may need adjustment.

### Reading `tool_audit_log`

`tool_audit_log` records every MCP tool call and related audit hook activity.

Useful query:

```sql
SELECT id, tool_name, success, error, duration_ms, called_at
FROM tool_audit_log
ORDER BY called_at DESC
LIMIT 40;
```

To show only failures:

```sql
SELECT tool_name, arguments, error, called_at
FROM tool_audit_log
WHERE success = 0
ORDER BY called_at DESC;
```
