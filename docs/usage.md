# Tally Usage Guide

## Starting Tally

```bash
.venv/bin/python3 tally.py
```

On startup Tally runs a dependency check, then prints the tool discovery summary:

```
Tally - Dependency Check
========================
 Dependency         | Type         | Status           | Install Hint
 python             | python       | v 3.11.2         |
 chromadb           | package      | v 1.5.2          |
 ollama             | package      | v installed      |
 ...
 nmap               | system_tool  | v available      |
 semgrep            | system_tool  | ! NOT FOUND      | pip install semgrep

Warning: 1 optional tool not found. Some scan features will be unavailable.

[*] Discovering tools...
  v nmap                 network    project      available
  ! semgrep              sast       repository   NOT INSTALLED
  ...
Loaded 8 tools (2 available, 6 not installed)

╭─ Welcome ───────────────────────────────────╮
│ Tally Web App Pentesting REPL v1.0          │
│ LlamaIndex + Chroma + Ollama                │
│ Active Project: No active project           │
╰─────────────────────────────────────────────╯

[no-project]>
```

Missing optional tools are skipped automatically — you do not need to install all tools to use Tally.

If a required Python package is missing, Tally prints an error and exits with code 1. Run `bash install.sh` to fix this.

### Startup Flags

```bash
# Check dependency status and exit without starting the REPL
.venv/bin/python3 tally.py --check

# Skip dependency check entirely (useful during development)
.venv/bin/python3 tally.py --skip-checks
```

---

## Creating a Project

Tally organizes all scans and findings by project. Before scanning, you need an active project.

```
[no-project]> new-project
```

Tally prompts you interactively:

```
Project name: acme-pentest
✓ Project created: acme-pentest
[acme-pentest]>
```

The new project becomes the active project immediately. The prompt changes to show `[acme-pentest]>`.

Project files are created under `projects/acme-pentest/`:

```
config/
  project.json         # Project metadata
  repositories.json    # Configured repositories
  nmap_hosts.json      # Nmap scan profiles (starts empty: {})
  endpoints/           # Per-repo API endpoint configs
chroma_db/             # RAG vector store
tool_outputs/          # Raw tool output files
  nmap/
  semgrep/
  ...
sessions/              # Chat history
reports/               # Generated reports
```

---

## Adding Repositories

A repository represents a codebase to scan. Add one with:

```
[acme-pentest]> add-repo
```

You are prompted for:
- **Name** — a short identifier (e.g. `api-server`)
- **Path** — absolute filesystem path to the repository
- **Languages** — comma-separated (e.g. `python,javascript`)
- **Base URLs** — API base URLs for ZAP scanning (optional, press Enter to skip)

```
[acme-pentest]> add-repo
Repository name: api-server
Path: /home/user/projects/acme/api
Languages (comma-separated): python
Base URLs (comma-separated, optional):
✓ Repository added: api-server
```

View configured repositories:

```
[acme-pentest]> repos
 Name        | Path                         | Languages | Base URLs
 api-server  | /home/user/projects/acme/api | python    | —
```

Edit or remove a repository:

```
[acme-pentest]> edit-repo api-server
[acme-pentest]> delete-repo api-server
```

---

## Running Scans

### Full Scan

Runs all segments (network, sast, sca, secrets, api) in order across all configured repositories. The network segment uses nmap profiles from `nmap_hosts.json`.

```
[acme-pentest]> scan
```

Tally prompts for approval before each tool execution:

```
Full Scan: acme-pentest
──────────────────────────────────────────────────

NETWORK
  [*] Running nmap (management)...
Run nmap? [y/N]: y
  ✓ nmap/management         | 4 findings    | 12.3s

SAST
  [*] Running semgrep (api-server)...
Run semgrep? [y/N]: y
  ✓ semgrep/api-server      | 7 findings    | 45.1s
...

Scan complete: 5 passed, 0 failed, 2 skipped | 28 findings ingested | 89.4s total
```

Auto-approve all tool executions without prompting:

```
[acme-pentest]> scan -y
```

### Segment Scan

Run a single segment across all repositories:

```
[acme-pentest]> scan -s sast
[acme-pentest]> scan -s sca
[acme-pentest]> scan -s secrets
[acme-pentest]> scan -s api
[acme-pentest]> scan -s network
```

Valid segments: `network`, `sast`, `sca`, `secrets`, `api`

### Single Tool Scan

```
[acme-pentest]> scan -t semgrep
[acme-pentest]> scan -t osv-scanner
[acme-pentest]> scan -t gitleaks
[acme-pentest]> scan -t pip-audit
[acme-pentest]> scan -t npm-audit
[acme-pentest]> scan -t composer-audit
[acme-pentest]> scan -t zap
```

For nmap, you can optionally specify a profile name. Without a profile name, all configured profiles run:

```
[acme-pentest]> scan -t nmap
[acme-pentest]> scan -t nmap management
```

### Timeout

All scan commands accept `--timeout <seconds>` (default: 300):

```
[acme-pentest]> scan -t nmap --timeout 600
[acme-pentest]> scan -s sca --timeout 120
```

### Repo Scan

Runs all language-appropriate tools for a single repository. Tool selection is automatic based on the repository's configured languages:

- Always runs: semgrep, osv-scanner, gitleaks, zap
- Python repos: adds pip-audit
- JavaScript/TypeScript/Node repos: adds npm-audit
- PHP repos: adds composer-audit

```
[acme-pentest]> repo-scan api-server
```

If you have only one repository, the name is optional:

```
[acme-pentest]> repo-scan
```

With multiple repositories and no name, Tally presents an interactive selection menu.

Additional flags:

```
# Auto-approve all tool executions
[acme-pentest]> repo-scan api-server -y

# Exclude directories from scanning
[acme-pentest]> repo-scan api-server --exclude tests,vendor,node_modules

# Filter findings by minimum severity
[acme-pentest]> repo-scan api-server --severity high

# Export results to a file
[acme-pentest]> repo-scan api-server --export /tmp/api-server-results.json
```

Valid severity values: `critical`, `high`, `medium`, `low`

### Raw Tool Execution

Run a tool with custom arguments, bypassing orchestration:

```
[acme-pentest]> run nmap --timeout 120 -sV 192.168.1.0/24
```

Tally asks if you want to ingest the output into the knowledge base after execution.

---

## Working with Findings

Findings are automatically ingested into the RAG knowledge base after each scan. You can then search, chat, and get statistics.

### Search

Semantic search over all ingested findings:

```
[acme-pentest]> search SQL injection vulnerabilities
```

Output:

```
 Finding                                              | Tool      | Type     | Relevance
 Potential SQL injection in user input handler...     | semgrep   | sast     | 0.142
 Unparameterized query detected at api/users.py:44... | semgrep   | sast     | 0.198
 ...
```

Results are sorted by semantic distance (lower = more relevant).

### Chat

Ask a question about the findings using RAG-augmented LLM chat:

```
[acme-pentest]> chat What are the most critical vulnerabilities found?
[acme-pentest]> chat Are there any exposed admin endpoints?
[acme-pentest]> chat Summarize the open ports and services found by nmap
```

Tally retrieves relevant findings from the knowledge base and passes them to the Ollama LLM as context. The response appears in a panel:

```
╭─ Assistant ─────────────────────────────────────────────╮
│ Based on the scan findings, the most critical issues    │
│ are:                                                    │
│ 1. SQL injection risk at api/users.py (semgrep)         │
│ 2. Exposed admin endpoint on port 8080 (nmap)           │
│ ...                                                     │
╰─────────────────────────────────────────────────────────╯
```

### Stats

View a summary of what has been ingested:

```
[acme-pentest]> stats
 Metric            | Value
 Total Documents   | 42
   nmap            | 8
   semgrep         | 18
   gitleaks        | 4
   pip-audit       | 12
   Severity: high  | 6
   Severity: medium| 22
   Severity: low   | 14
 Last Updated      | 2024-01-15 10:34:22
```

---

## Purging Data

Remove findings from the knowledge base when you want to re-scan cleanly.

```
# Delete all findings from a specific tool
[acme-pentest]> purge --tool semgrep

# Delete findings for a specific tool+profile combination
[acme-pentest]> purge --tool nmap --profile management

# --profile requires --tool
[acme-pentest]> purge --profile management   # Error: requires --tool
```

Tally shows a count and prompts for confirmation before deleting:

```
Found 18 document(s). Delete all semgrep findings? [y/N] y
Deleted 18 document(s).
```

---

## Generating Reports

Reports aggregate all findings currently in the knowledge base.

```
# Markdown report (default) — saved to projects/[name]/reports/report_<timestamp>.md
[acme-pentest]> report

# HTML report — self-contained, suitable for sharing
[acme-pentest]> report --format html

# JSON report — machine-readable, full data
[acme-pentest]> report --format json

# Write to a specific path
[acme-pentest]> report --output /tmp/acme-report.html --format html
```

Output:

```
✓ Report saved: projects/acme-pentest/reports/report_2024-01-15_103422.md
```

The Markdown report contains:
- Executive summary (total findings, counts by severity)
- Network findings table (nmap open ports)
- SAST findings table (semgrep)
- SCA findings tables (osv-scanner, pip-audit, npm-audit, composer-audit)
- Secrets table (gitleaks, without secret values)
- API findings table (ZAP alerts)

---

## Switching Between Projects

```
# List all projects
[acme-pentest]> projects

 Name          | Created    | Repositories | Active
 → acme-pentest| 2024-01-14 | 2            | ✓
 corp-audit    | 2024-01-10 | 1            |

# Switch to a different project
[acme-pentest]> switch corp-audit
✓ Switched to project: corp-audit
[corp-audit]>

# View active project details
[corp-audit]> project-info
╭─ Project: corp-audit ──────────────────────────╮
│ Created: 2024-01-10                             │
│ Repositories: 1                                 │
│                                                 │
│ Repositories:                                   │
│   • webapp (python, javascript)                 │
╰─────────────────────────────────────────────────╯
```

Each project has completely isolated findings, chat history, and reports. Switching projects does not affect the other project's data.
