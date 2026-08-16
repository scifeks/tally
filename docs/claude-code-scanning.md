# Claude Code Scanning

## Overview

Claude Code scanning is an LLM-driven SAST capability that runs inside Claude Code
sessions. It maps your codebase's attack surface first (entry points, inputs, call
graph, trust boundaries), then dispatches specialized scanner agents per code
partition to trace user-controlled data to dangerous sinks. Unreachable code is
swept separately for latent vulnerabilities.

Unlike Tally's CLI-based tool scanning (Semgrep, Psalm, Gitleaks), Claude Code
scanning uses language model pattern matching guided by per-language detection
matrices. It does not require installing external tool binaries. It covers Python,
PHP, JavaScript, and TypeScript.

Findings are submitted to Tally through the MCP server, where they appear alongside
tool-generated findings in reports, the web UI, and triage workflows.

---

## Prerequisites

- Tally installed and configured with at least one project
- Python 3.12+ with Tally's virtual environment activated
- Claude Code installed (CLI, desktop app, or IDE extension)
- The Tally scanner skills available in your Claude Code session

---

## Setup

### Step 1: Create an MCP bearer token

Start Tally and create a token for MCP authentication:

```
tally> mcp token create scanning
```

Tally prints the token once. Copy and store it securely. You cannot retrieve it
later; if lost, revoke and create a new one.

Other token management commands:

```
tally> mcp token list
tally> mcp token revoke scanning
```

### Step 2: Start the MCP server

In a separate terminal, start the MCP SSE server:

```bash
source .venv/bin/activate
python3 tally-cli.py mcp
```

The server binds to `127.0.0.1:8765` by default. Override the port with `--port`:

```bash
python3 tally-cli.py mcp --port 9000
```

Or set `mcp_port` in `config/global.json`:

```json
{
  "mcp_port": 9000
}
```

The MCP server runs as a blocking process. Keep it running for the duration of your
scanning session.

### Step 3: Configure Claude Code to connect

Add Tally's MCP server to the `.mcp.json` file in the project you want to scan:

```json
{
  "mcpServers": {
    "tally": {
      "type": "sse",
      "url": "http://127.0.0.1:8765/sse"
    }
  }
}
```

If you changed the port, update the URL to match.

You can also add this to your Claude Code user settings for global availability. See
Claude Code's MCP documentation for user-level configuration.

### Step 4: Make scanner skills and agents available

The scanner skills live in Tally's `.claude/skills/` directory and the agent
definitions live in `.claude/agents/`. To use them from another project, copy or
symlink both to your Claude Code paths:

```bash
cp -r /path/to/tally/.claude/skills/tally-scan-* ~/.claude/skills/
cp -r /path/to/tally/.claude/agents/tally-scan-* ~/.claude/agents/
```

Or create symlinks:

```bash
ln -s /path/to/tally/.claude/skills/tally-scan-* ~/.claude/skills/
ln -s /path/to/tally/.claude/agents/tally-scan-* ~/.claude/agents/
```

The agent definitions control model selection and tool access for the recon and
scanner subagents. Without them, the orchestrator falls back to generic agent
dispatch.

If you run Claude Code from within the Tally project directory, skills and agents
are discovered automatically.

---

## Running a Scan

Invoke the orchestrator skill:

```
/tally-scan-external
```

The orchestrator runs a multi-phase pipeline.

### Phase 1: Setup

1. **Project selection.** Lists your Tally projects and asks which one to scan.
2. **Run mode.** Continue a previous scan run or start a new one.
3. **Adversarial verification.** Optionally enable a courtroom-style verification
   pass that filters false positives before submission (see below).

### Phase 2: Reconnaissance

The orchestrator dispatches a recon agent (running on Sonnet for speed) that maps
the codebase before any vulnerability scanning begins. Recon produces a manifest
with:

- **Entry points.** HTTP routes, CLI handlers, GraphQL resolvers, WebSocket
  handlers, queue consumers, and cron jobs discovered via framework-specific grep
  patterns.
- **Input inventory.** A numbered table of user-controlled inputs for each entry
  point (query params, body fields, headers, cookies, path variables, file uploads,
  CLI args).
- **Call graph.** A two-level trace from each entry point handler to the
  application functions it calls and the dangerous sinks those functions reach.
- **Trust boundaries.** Where authentication middleware is applied, where data
  crosses to databases, external APIs, file systems, and subprocesses.
- **Scope partitions.** Entry points that share application-specific code are
  grouped into partitions via union-find. Each partition becomes an independent
  unit of work for scanner agents.
- **Dead code inventory.** Source files not reachable from any entry point. These
  are scanned separately with lower confidence defaults.

If recon fails, the orchestrator falls back to dispatching individual scanner
skills against the full repo without recon context.

### Phase 3: Domain family scanning

The 47 scanner skills are grouped into 10 domain families: injection, XSS,
access control, authentication, crypto, data integrity, design logic,
misconfiguration, JWT, and network.

For each partition from the recon manifest, the orchestrator dispatches one domain
agent per relevant family. Each agent receives its partition's scope (entry points,
inputs, files, trust boundaries) and all the skill references for its family. The
agent traces each numbered input forward through the call graph to dangerous sinks,
applying detection patterns from its family's skills.

Families are skipped when a partition contains none of the family's relevant
languages. The JWT family is additionally skipped when no JWT library imports are
present.

### Phase 4: Dead code sweep

After domain agents finish, the orchestrator dispatches sweep agents against the
dead code inventory from recon. Sweep agents use pattern-based detection (not
input-forward tracing, since dead code has no inputs to trace from). All dead code
findings default to `finding_type: weakness` and `confidence: potential` because the
code is not currently exploitable. Severity reflects the pattern's inherent danger.

Dead code matters because it can be activated by a variable change, a spelling fix,
or an import addition. Reporting it as a weakness gives developers visibility into
latent risk.

### Classification gates

Every finding (from both domain agents and dead code sweep) passes through four
classification gates that adjust severity, confidence, and finding type. Gates
classify findings, they do not eliminate them.

1. **Reachability.** Is the code reachable from a production entry point? Dev-only
   paths are downgraded to `weakness`.
2. **Attacker control.** Is the input actually attacker-controlled? Server-generated
   or config-sourced inputs reduce confidence.
3. **Sanitization.** Is there effective sanitization between source and sink? Context
   mismatches (HTML sanitizer on a SQL sink) are flagged explicitly.
4. **Impact.** Does exploiting this give a meaningful new capability? Limited reads
   and self-only writes are downgraded.

Gate results are recorded in each finding's `reasoning` field and
`meta.gate_results` for downstream review.

### Phase 5: Adversarial verification (optional)

When enabled, the orchestrator passes all collected findings through the
`tally-scan-adversarial` skill before submission. For each finding, three
independent deep-investigator agents run in parallel:

- **Prosecutor**: builds the case that the vulnerability is real
- **Defense**: argues it is a false positive
- **Expert witness**: gathers objective evidence

The orchestrator acts as judge, reads the code, and decides whether each finding
survives. Tie goes to prosecution (a false negative is worse than a false positive
in security scanning).

Adversarial verification is off by default. Enable it when you want higher precision
at the cost of longer scan time.

### Phase 6: Submission and dedup

The orchestrator submits each finding to Tally through the MCP server, runs a
required deduplication pass to group candidate duplicates by file, rule, and line
proximity, then closes the scan run. A summary reports: recon results, agent
dispatch counts, findings collected, accepted, rejected, and deduplicated.

---

## Vulnerability Categories

The scanner covers these vulnerability classes:

| Category | Skills | Examples |
|---|---|---|
| Access Control | CSRF, IDOR/BOLA, incorrect authz, missing authz, open redirect, path traversal, mass assignment | Missing CSRF tokens, direct object references without ownership checks |
| Authentication | Session management, weak/missing authn | Session fixation, missing login checks |
| Cryptography | Hardcoded secrets, PII in logs, PII in response, weak algorithm, weak hashing, weak PRNG | API keys in source, MD5 for passwords |
| Data Integrity | File upload, insecure deserialization, missing integrity verification | Unrestricted file types, pickle.loads on user data |
| Design Logic | Missing exception handling, order of operations, TOCTOU, race conditions, insufficient logging | Silent exception swallowing, check-then-act without locking |
| Injection | SQL, LDAP, NoSQL, OS command, reflection, template, XPath, eval, header, prototype pollution | f-string SQL queries, unsanitized shell commands |
| Misconfiguration | CORS, CSP, error messages, framework defaults, JWT (3 variants), security headers, file permissions | Debug mode in production, missing HSTS |
| SSRF | Server-side request forgery | Fetching user-supplied URLs without allowlist |
| XSS | Reflected, stored, blind | Unescaped user input in templates |
| XXE | XML external entity | DTD processing on untrusted XML |

Each skill covers Python, PHP, JavaScript, and TypeScript with framework-specific
detection patterns.

---

## MCP Tools Reference

All tools require `auth_token` as a named parameter.

| Tool | Parameters | Returns | Purpose |
|---|---|---|---|
| `list_projects` | `auth_token` | `[{project_id, project_name, path, latest_run_id}]` | Enumerate active projects |
| `create_scan_run` | `project, project_id, repo_ids, auth_token` | `{run_id}` | Open a new scan run |
| `submit_finding` | `project, project_id, repo_id, run_id, finding, auth_token` | `{finding_id, status}` | Submit one finding |
| `get_duplicate_candidates` | `project, run_id, auth_token` | `{groups: [[id, ...]]}` | Find candidate duplicate groups |
| `resolve_duplicates` | `project, run_id, survivor_id, removed_ids, auth_token` | `{status, count}` | Mark losers as duplicates |
| `end_scan` | `project, project_id, run_id, auth_token` | `{status}` | Close a scan run |
| `fetch_batch` | `project, auth_token` | `{batch_id, findings, ...}` | Fetch next triage batch |
| `submit_verdicts` | `project, batch_id, verdicts, auth_token` | `{accepted, rejected}` | Submit triage verdicts |
| `skip_batch` | `project, batch_id, auth_token` | `{status}` | Skip a triage batch |

---

## Troubleshooting

### Connection refused

Verify the MCP server is running and the port matches your `.mcp.json`:

```bash
curl -s http://127.0.0.1:8765/sse
```

If the port was changed in `config/global.json`, update the URL in `.mcp.json` to
match.

### Invalid or missing MCP token

The MCP server returns `PermissionError("Invalid or missing MCP token")` when the
bearer token is wrong or expired. Create a new token with `mcp token create` in the
Tally REPL.

### Findings rejected

If a scanner's findings are systematically rejected, the scanner skill has a payload
bug. The MCP validator is deterministic: a rejected payload will not succeed on
retry. Check the error message for the specific field that failed validation.

### Scanner skill not found

If `tally-scan-external` reports no scanner skills installed, verify the skill
directories are present in `.claude/skills/` (project-level) or `~/.claude/skills/`
(user-level). Each skill directory must contain a `SKILL.md` file.
