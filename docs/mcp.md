# MCP Triage System

## 1. Overview

Tally's MCP triage system uses Claude Code as an automated security analyst. After
you run scans and ingest findings into a project's SQLite database, the `triage`
command launches Claude Code as a subprocess, connects it to Tally's MCP server, and
has it read and update every untriaged finding — all without requiring manual
interaction.

The triage system solves the volume problem: a single scan session can produce dozens
or hundreds of findings, many of which are false positives or low-signal. Claude reads
each finding, inspects the relevant source code or dependency data using the allowed
tools, and writes a structured `triage` record into the finding's `meta` field that
includes a confidence level, reasoning, attack vector, and remediation advice.

During a session the orchestrator writes a temporary `.mcp.json` to the project root,
launches Claude Code as a non-interactive subprocess with `--dangerously-skip-permissions`,
waits for it to finish, then removes `.mcp.json`. Claude communicates with the Tally MCP
server over stdio. All tool calls — including file reads and finding updates — are logged
to the `tool_audit_log` table in the findings database.

---

## 2. Prerequisites

### Claude Code

Claude Code must be installed and the `claude` binary must be on your `PATH`. Verify
with:

```bash
claude --version
```

If Claude Code is not installed, follow the instructions at
https://docs.anthropic.com/claude-code.

### Anthropic API key

Claude Code requires an Anthropic API key. Set it in your shell environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Python dependencies

Tally's install script installs all required packages including the `mcp` SDK:

```bash
bash install.sh
```

If you need to install just the MCP dependency manually:

```bash
.venv/bin/pip install mcp
```

### A project with completed scans

The `triage` command queries `findings WHERE triaged_at IS NULL`. If the active project
has no findings in its SQLite database, triage exits immediately with zero sessions run.
Run at least one scan and ingest its output before triaging:

```
scan --tool=semgrep
```

---

## 3. Claude Code Setup

### `.mcp.json`

Claude Code discovers MCP server configuration by looking for `.mcp.json` in its working
directory. You do not write or edit this file — Tally generates it automatically at the
start of every triage session and deletes it when the session ends.

The generated file looks like this (with the active project name substituted):

```json
{
  "mcpServers": {
    "tally-mcp": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "-m",
        "tally_mcp.server",
        "--project",
        "<project-name>"
      ]
    }
  }
}
```

Because Claude Code looks for `.mcp.json` in its working directory, the orchestrator
must be invoked from the Tally application root (the directory that contains `tally.py`).
The Tally REPL does this automatically. If you invoke `tally_mcp/orchestrator.py` directly,
run it from the project root:

```bash
.venv/bin/python3 -m tally_mcp.orchestrator --project <name>
```

### `.claude.json` — tool allowlist and hooks

The file `.claude.json` in the Tally root configures which tools Claude Code is allowed
to call and which hooks run on every tool use. Its exact contents are:

```json
{
  "permissions": {
    "allow": [
      "mcp__tally-mcp__get_finding",
      "mcp__tally-mcp__get_findings_batch",
      "mcp__tally-mcp__get_project_config",
      "mcp__tally-mcp__update_finding",
      "mcp__tally-mcp__update_findings_batch",
      "Read(*)",
      "Grep(*)",
      "Glob(*)"
    ],
    "deny": []
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [{"type": "command", "command": "python3 tally_mcp/hooks/pre_tool_use.py"}]
      }
    ]
  }
}
```

**Allowed tools and what they do:**

| Permission | What it allows |
|---|---|
| `mcp__tally-mcp__get_finding` | Fetch a single finding by its database ID |
| `mcp__tally-mcp__get_findings_batch` | Fetch a filtered batch of findings for triage |
| `mcp__tally-mcp__get_project_config` | Read the project's `project.json` to resolve repository paths |
| `mcp__tally-mcp__update_finding` | Write triage results back to a single finding |
| `mcp__tally-mcp__update_findings_batch` | Write triage results to multiple findings in one call |
| `Read(*)` | Read any file on disk — required to inspect source code during triage |
| `Grep(*)` | Search file contents — required to locate route handlers and code patterns |
| `Glob(*)` | List files by pattern — required to resolve file paths |

Claude Code is not allowed to write files, run shell commands, or access the network.

### `PreToolUse` hook

Every tool call Claude attempts — including MCP tools and file operations — triggers
`tally_mcp/hooks/pre_tool_use.py` before the call executes. The hook reads a JSON payload
from stdin, looks up the active project from `.mcp.json`, and inserts a row into the
`tool_audit_log` table with the tool name, arguments, and a UTC timestamp.

This provides a complete audit trail of everything Claude attempted during a session.
The MCP server also writes audit rows after each call completes, so the log contains
both the pre-call record (from the hook) and a post-call record with success/failure
and duration.

### `--dangerously-skip-permissions`

The orchestrator invokes Claude Code with `--dangerously-skip-permissions`. This flag
tells Claude Code to skip its interactive permission prompts and trust the allowlist in
`.claude.json` instead. In practice it means Claude can call the allowed tools without
pausing to ask the user for approval on each one.

This is safe in the triage context because the allowlist only permits read operations
and the Tally MCP tools. It does not allow arbitrary shell execution or file writes.
Do not enable this flag in Claude Code sessions outside of Tally's automated triage
pipeline unless you understand the implications.

---

## 4. Configuration

All three MCP config values live under the top-level keys of `config/global.json` and
are validated by `GlobalConfig` in `core/config/schemas.py`. If the config file is not
found, `tally_mcp/config.py` falls back to the defaults shown below.

### `mcp_batch_size`

**Default:** `10`
**Constraint:** must be ≥ 1

Controls the maximum number of findings returned by a single `get_findings_batch` call.
The MCP tool enforces this ceiling regardless of what Claude requests.

Increase this if you have a large number of findings per strategy and want fewer Claude
sessions. Decrease it if sessions are timing out before Claude finishes processing all
findings — a smaller batch reduces the per-session workload.

Tradeoff: larger batches mean more context per session (higher token usage and longer
runtime); smaller batches mean more sessions and more Claude API overhead.

### `mcp_batch_timeout_seconds`

**Default:** `30`
**Constraint:** must be ≥ 1

The number of seconds `get_findings_batch` will wait for the SQLite query to return
before giving up. On timeout the tool writes a failed audit row and returns an empty
list. This is expected and intentional — see [Troubleshooting](#8-troubleshooting).

Increase this only if your findings database is very large and queries are legitimately
taking longer than 30 seconds.

### `mcp_session_timeout_seconds`

**Default:** `300` (5 minutes)

The number of seconds the orchestrator will wait for a single Claude Code subprocess
to complete before killing it and recording the session as failed.

Increase this if Claude sessions are timing out before finishing large batches. Decrease
it if you want faster failure detection when something goes wrong.

---

## 5. Running Triage

### Command

From inside the Tally REPL with an active project:

```
triage
```

The command takes no flags. It uses the active project set with `project switch <name>`.

### What happens step by step

1. **DB query** — The orchestrator connects to
   `projects/<name>/sqlite/findings.db` and fetches all rows where
   `triaged_at IS NULL`, collecting each finding's `id` and `tool`.

2. **Strategy grouping** — Each finding is assigned a strategy based on its tool:

   | Tool | Strategy |
   |---|---|
   | `semgrep` | `code_trace` |
   | `zap` | `api_trace` |
   | `osv-scanner`, `pip-audit`, `npm-audit`, `composer-audit` | `dependency` |
   | `gitleaks` | `enrich_only` |
   | `nmap`, `tree-sitter` | skipped — not triaged |

   Findings from skipped tools are counted and logged but otherwise ignored.

3. **`.mcp.json` written** — The orchestrator writes the server configuration to
   `.mcp.json` in the application root.

4. **Claude session per strategy** — For each strategy that has at least one finding,
   the orchestrator renders a prompt (from `tally_mcp/prompts/<strategy>.py`), then runs:

   ```bash
   claude --print --dangerously-skip-permissions "<prompt text>"
   ```

   The prompt tells Claude the finding IDs to process and the exact MCP tool sequence
   to follow. Claude calls `get_findings_batch` to retrieve findings, reads source files
   as needed, then calls `update_findings_batch` with results for all findings before
   exiting.

5. **Audit check** — After the subprocess exits, the orchestrator queries
   `tool_audit_log` to count `update_finding` and `update_findings_batch` calls made
   since the session started. If the count is zero, the session is recorded as
   `incomplete`.

6. **Cleanup** — `.mcp.json` is deleted regardless of whether sessions succeeded or
   failed.

### Session result output

The REPL prints a one-line summary when triage finishes:

```
Triage: 2 sessions run, 2 success, 0 failed, 0 incomplete
```

- **sessions_run** — number of strategies that had untriaged findings
- **success** — sessions where at least one finding was updated
- **failed** — sessions that timed out or where Claude exited non-zero
- **incomplete** — sessions where Claude exited zero but made no update calls

### Verifying results

Check that findings were updated:

```bash
sqlite3 projects/<name>/sqlite/findings.db \
  "SELECT COUNT(*) FROM findings WHERE triaged_at IS NOT NULL"
```

---

## 6. Understanding Triage Output

When Claude calls `update_finding`, the tool writes a `triage` key into the finding's
`meta` JSON column. The structure is:

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
    "triaged_by": "claude-code",
    "triaged_at": "2025-11-04T14:23:01.456789+00:00",
    "strategy": "code_trace"
  }
}
```

### Field reference

**`confidence`**
Claude's assessment of whether the finding is a real vulnerability. Valid values:
- `confirmed` — Claude traced the full exploit path through real code
- `probable` — strong evidence but the trace was incomplete (e.g. dynamic dispatch,
  unreadable helper)
- `potential` — plausible but evidence is indirect or the file could not be read
- `false_positive` — Claude determined the finding is safe in context

**`previous_confidence`**
The confidence value the finding had before triage. Preserved so you can see whether
triage upgraded, downgraded, or confirmed the original scanner assessment.

**`reasoning`**
Claude's analysis chain: what it read, what it found, and why it assigned the
confidence it did. This is the primary field to read when reviewing a triage decision.

**`remediation`**
A specific, actionable fix. For code findings this is a concrete code change; for
dependency findings it is an upgrade target or replacement package; for secrets it is
a three-step remove/rotate/replace procedure.

**`attack_vector`**
For web findings: the HTTP method, path, and parameter(s) involved. For dependency
findings: the CVSS attack surface description. For secrets: the access path (e.g.
`any actor with repo read access`). `null` when no attack vector is applicable.

**`call_stack`**
For `code_trace` confirmed findings: a list of `"file:line function"` strings tracing
from the HTTP entry point to the vulnerable sink, outermost first. `null` for all other
strategies and for unconfirmed findings.

**`triaged_by`**
Always `"claude-code"` for automated triage sessions.

**`triaged_at`**
ISO 8601 UTC timestamp of when `update_finding` was called.

**`strategy`**
The triage strategy used for this finding (`code_trace`, `api_trace`, `dependency`,
or `enrich_only`).

> **Note:** `requires_human_review` is referenced in some planning documents but is
> not implemented in the current codebase. It does not appear in the triage output.

---

## 7. Querying Triage Results

All queries below run against `projects/<name>/sqlite/findings.db`. Open the database
with:

```bash
sqlite3 projects/<name>/sqlite/findings.db
```

### All findings triaged in the last session

```sql
SELECT id, tool, severity, confidence, triaged_at
FROM findings
WHERE triaged_at IS NOT NULL
ORDER BY triaged_at DESC
LIMIT 50;
```

### All confirmed vulnerabilities

```sql
SELECT id, tool, file, severity, triaged_at
FROM findings
WHERE confidence = 'confirmed'
  AND triaged_at IS NOT NULL
ORDER BY severity, tool;
```

### All false positives

```sql
SELECT id, tool, file, severity
FROM findings
WHERE confidence = 'false_positive'
ORDER BY tool, file;
```

### Findings where confidence was lowered during triage

The `previous_confidence` value is stored inside the `meta` JSON column. This query
compares the current confidence against the pre-triage value:

```sql
SELECT id, tool, confidence,
       json_extract(meta, '$.triage.previous_confidence') AS previous_confidence
FROM findings
WHERE triaged_at IS NOT NULL
  AND json_extract(meta, '$.triage.previous_confidence') != confidence
ORDER BY id;
```

### Findings where confidence was raised during triage

```sql
SELECT id, tool, confidence,
       json_extract(meta, '$.triage.previous_confidence') AS previous_confidence
FROM findings
WHERE triaged_at IS NOT NULL
  AND json_extract(meta, '$.triage.previous_confidence') != confidence
  AND confidence IN ('confirmed', 'probable')
ORDER BY id;
```

---

## 8. Troubleshooting

### Claude starts but makes no MCP tool calls

**Symptom:** The triage session runs and exits cleanly, but no findings are updated and
`tool_audit_log` shows no MCP calls.

**Cause:** Claude Code did not find `.mcp.json`. This happens when the `cwd` passed to
the subprocess is wrong.

**Fix:** Confirm that the `triage` command is being run from inside the Tally REPL
started from the application root (the directory containing `tally.py`). If you are
invoking `tally_mcp/orchestrator.py` directly, run it from the application root:

```bash
cd /path/to/tally
.venv/bin/python3 -m tally_mcp.orchestrator --project <name>
```

Do not `cd` into `tally_mcp/` before running the orchestrator.

### Session completes but no findings are updated

**Symptom:** The REPL shows `1 incomplete` (or similar). The `tool_audit_log` contains
`get_findings_batch` calls but no `update_finding` or `update_findings_batch` calls.

**Cause:** Claude exited without calling an update tool. This can happen if the prompt
was not understood, if `get_findings_batch` returned an empty list, or if Claude
encountered an error it could not recover from.

**Diagnosis:** Check the audit log for the session:

```sql
SELECT tool_name, success, error, called_at
FROM tool_audit_log
ORDER BY called_at DESC
LIMIT 20;
```

If `get_findings_batch` returned successfully but no update was called, the issue is
likely in the Claude session itself. There is no session transcript stored in the
database; re-running triage with a smaller batch size may help isolate the problem.

### Batch never fills / `get_findings_batch` returns empty

**Symptom:** `get_findings_batch` always returns `[]`.

**Cause:** This is expected behaviour when the query takes longer than
`mcp_batch_timeout_seconds` (default 30s). On timeout, the tool writes a failed audit
row and returns an empty list rather than raising an error. Claude then has nothing to
update and the session completes as `incomplete`.

**Fix:** Increase `mcp_batch_timeout_seconds` in `config/global.json`:

```json
{
  "mcp_batch_timeout_seconds": 60
}
```

### Invalid field values rejected by `update_finding`

**Symptom:** `tool_audit_log` shows `update_finding` calls with `success = 0` and an
error like `Invalid confidence: 'high'. Must be one of: ...`

**Cause:** Claude passed a value that is not in the allowed set. Valid values are:

- `confidence`: `confirmed`, `probable`, `potential`, `false_positive`
- `severity`: `critical`, `high`, `medium`, `low`, `informational`
- `finding_type`: `secret`, `vulnerability`, `weakness`, `misconfiguration`,
  `exposure`, `dependency`, `informational`

This is a model output issue. Retrying the session may produce valid values. If it
recurs consistently, the prompt template for the affected strategy may need adjustment.

### Reading the `tool_audit_log` to debug a session

The `tool_audit_log` table records every tool call from both the PreToolUse hook
(before the call) and the MCP server (after the call completes with duration and
error).

Schema:

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Autoincrement primary key |
| `tool_name` | TEXT | Name of the tool called |
| `arguments` | TEXT | JSON-serialised arguments |
| `success` | INTEGER | 1 = succeeded, 0 = failed |
| `error` | TEXT | Error message if success = 0, otherwise NULL |
| `duration_ms` | INTEGER | Call duration in milliseconds (NULL for pre-call hook rows) |
| `called_at` | TEXT | ISO 8601 UTC timestamp |

Useful query to see the full timeline of a recent session:

```sql
SELECT id, tool_name, success, error, duration_ms, called_at
FROM tool_audit_log
ORDER BY called_at DESC
LIMIT 40;
```

To see only failures:

```sql
SELECT tool_name, arguments, error, called_at
FROM tool_audit_log
WHERE success = 0
ORDER BY called_at DESC;
```
