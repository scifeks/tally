# Claude Code Scanning

## Overview

Claude Code scanning is an LLM-driven SAST capability that runs inside Claude Code
sessions. It scans your repository for security vulnerabilities across Python, PHP,
JavaScript, and TypeScript by dispatching parallel scanner subagents, each specialized
in one vulnerability category.

Unlike Tally's CLI-based tool scanning (Semgrep, Psalm, Gitleaks), Claude Code
scanning uses language model pattern matching guided by per-language detection
matrices. It does not require installing external tool binaries.

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

### Step 4: Make scanner skills available

The scanner skills live in Tally's `.claude/skills/` directory. To use them from
another project, copy or symlink the skill directories to your Claude Code skills
path:

```bash
cp -r /path/to/tally/.claude/skills/tally-scan-* ~/.claude/skills/
```

Or create symlinks:

```bash
ln -s /path/to/tally/.claude/skills/tally-scan-* ~/.claude/skills/
```

If you run Claude Code from within the Tally project directory, the skills are
discovered automatically.

---

## Running a Scan

Invoke the orchestrator skill:

```
/tally-scan-external
```

The orchestrator walks you through:

1. **Project selection.** Lists your Tally projects and asks which one to scan.
2. **Run mode.** Continue a previous scan run or start a new one.
3. **Adversarial verification.** Optionally enable a courtroom-style verification
   pass that filters false positives before submission (see below).
4. **Scanner dispatch.** Dispatches all installed `tally-scan-*` skills in parallel.
   Each scanner covers one vulnerability category (SQL injection, XSS, CSRF, etc.).
5. **Finding submission.** Submits each finding to Tally through the MCP server.
6. **Dedup pass.** Groups candidate duplicates and picks survivors.
7. **Summary.** Reports how many skills ran, how many findings were submitted,
   accepted, rejected, and deduplicated.

### Adversarial Verification

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
