# Tally Usage Guide

## Starting Tally

```bash
.venv/bin/python3 tally.py
```

On first run, if `config/commands.json` does not exist, Tally launches an interactive setup wizard that detects installed tools and configures how each one runs (locally or via Docker). After setup completes, the REPL starts normally.

On subsequent startups Tally runs a dependency check, then prints the tool discovery summary:

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
│ Tally Web App Security Auditing REPL v1.0          │
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
[no-project]> project add
```

Tally prompts you interactively:

```
Project name: acme-security-audit
✓ Project created: acme-security-audit
[acme-security-audit]>
```

The new project becomes the active project immediately. The prompt changes to show `[acme-security-audit]>`.

Project files are created under `projects/acme-security-audit/`:

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
[acme-security-audit]> repo add
```

Tally first asks for the execution mode, then collects the appropriate paths.

**Local mode** — the tool runs directly on the host:

- **Name** — a short identifier (e.g. `api-server`)
- **Mode** — `local` (default) or `docker`
- **Local path** — absolute filesystem path on the host (required in all modes)
- **Languages** — comma-separated (e.g. `python,javascript`); Tally auto-detects if blank
- **Base URLs** — API base URLs for ZAP scanning (optional, press Enter to skip)

```
[acme-security-audit]> repo add
Repository #1:
  Name: api-server
  Type: api
  Mode [local/docker] [local]:
  Local path: /home/user/projects/acme/api
  Languages (detected python) [python]:
  Base URLs (comma-separated, optional):
✓ Repository 'api-server' added to project 'acme-security-audit'
```

**Docker mode** — the tool runs via `docker exec` inside a running container.
A local path is still required so Tally can detect languages and run local tools:

```
[acme-security-audit]> repo add
Repository #1:
  Name: api-server
  Type: api
  Mode [local/docker] [local]: docker
  Docker container name: semgrep-container
  Docker mount point (path inside container): /mnt/api
  Local path (required for language detection and local tool execution): /home/user/projects/acme/api
  Languages (detected python) [python]:
  Base URLs (comma-separated, optional):
✓ Repository 'api-server' added to project 'acme-security-audit'
```

View configured repositories:

```
[acme-security-audit]> repo list
 Name        | Path                         | Languages | Base URLs
 api-server  | /home/user/projects/acme/api | python    | —
```

Edit or remove a repository:

```
[acme-security-audit]> repo edit api-server
[acme-security-audit]> repo delete api-server
```

When editing, Tally pre-fills current values — press Enter to keep them. Switching
from Docker mode to local mode automatically clears the Docker fields.

---

## Managing Tools

Tally stores tool configuration in `config/commands.json`. Use the `tool` commands to view and modify it from within the REPL.

### Listing Tools

```
[acme-security-audit]> tool list
```

Shows all configured tools, their execution mode (local or docker), and whether they are currently available.

### Adding a Tool

```
[acme-security-audit]> tool add
```

Tally lists tools that have a wrapper but are not yet configured. Select one by name or number and follow the prompts to configure the binary path (local) or container details (docker).

### Editing a Tool

```
[acme-security-audit]> tool edit semgrep
```

Re-runs the configuration interview for the named tool, pre-filling current values. Press Enter to keep an existing value.

### Removing a Tool

```
[acme-security-audit]> tool remove semgrep
```

Removes the tool from `config/commands.json`. Tally asks for confirmation before deleting.

### Per-Project Tool Overrides

Global tool configuration in `config/commands.json` applies to all projects. If a specific project needs a different binary path, Docker container, or other configuration for a tool, you can create a project-level override without affecting the global default.

Project-level overrides are stored in `projects/<name>/config/commands.json` and fully replace the global entry for the named tool whenever a scan runs against that project. Tools not listed in the project config continue to use the global config.

**Requires an active project** (`project add` or `project switch <name>`).

#### List project-level overrides

```
[acme-security-audit]> tool list --project=acme-security-audit
```

Shows only the overrides configured at the project level. If none exist, prints a message saying so.

#### Add a project-level override

```
[acme-security-audit]> tool add --project=acme-security-audit
```

Runs the same interactive interview as the global `tool add`. If the tool is already configured globally, Tally warns you that you are creating a project-level override before proceeding.

#### Edit a project-level override

```
[acme-security-audit]> tool edit semgrep --project=acme-security-audit
```

Re-runs the configuration interview for the named override, pre-filling the current project-level values. Does not fall back to the global config.

#### Remove a project-level override

```
[acme-security-audit]> tool remove semgrep --project=acme-security-audit
```

Removes the project-level override. The tool reverts to the global configuration. Tally asks for confirmation before deleting.

---

## Running Scans

### Full Scan

Runs all segments (network, sast, sca, secrets, api) in order across all configured repositories. The network segment uses nmap profiles from `nmap_hosts.json`.

```
[acme-security-audit]> scan
```

Tally prompts for approval before each tool execution:

```
Full Scan: acme-security-audit
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

### Scan Flags

Use flags to scope a scan. All flags accept comma-separated lists.

**Run specific tools:**

```
[acme-security-audit]> scan --tool=semgrep
[acme-security-audit]> scan --tool=semgrep,gitleaks
```

**Run all tools of a given type:**

Valid types: `network`, `sast`, `sca`, `secrets`, `api`

```
[acme-security-audit]> scan --type=sast
[acme-security-audit]> scan --type=sast,sca
```

**Scope to a single repository:**

```
[acme-security-audit]> scan --repo=api-server
```

If you have only one repository, `scan` (no flags) already targets it.

**Combine flags:**

```
[acme-security-audit]> scan --repo=api-server --tool=semgrep
[acme-security-audit]> scan --tool=semgrep --type=sast
```

Network tools (`nmap`) cannot be scoped to a repository.
Use `scan --tool=nmap` (without `--repo`) to run nmap.

### Docker vs Local Execution

Each tool runs in whichever mode is configured in `config/commands.json` — either locally as a subprocess or via `docker exec` inside a running container. From the scan commands' perspective, the execution mode is transparent: output is captured, parsed, and ingested identically regardless of whether a tool runs locally or in Docker.

To switch a tool from local to Docker (or vice versa):

```
[acme-security-audit]> tool edit semgrep
```

For Docker tools, repositories must have a `docker_path` set — the container-side mount path for the repository. This is set when adding or editing a repository with `repo add` / `repo edit`.

### Raw Tool Execution

Run a tool with custom arguments, bypassing orchestration:

```
[acme-security-audit]> run nmap --timeout 120 -sV 192.168.1.0/24
```

Tally asks if you want to ingest the output into the knowledge base after execution.

---

## Working with Findings

Findings are automatically ingested into the RAG knowledge base after each scan. You can then search, chat, and get statistics.

### Search

Structured search over all ingested findings using flags:

```
[acme-security-audit]> search --tool=semgrep
[acme-security-audit]> search --severity=high
[acme-security-audit]> search --type=sast --severity=high
[acme-security-audit]> search --rule~=injection
[acme-security-audit]> search --page=2 --page-size=20
```

Run `search --help` for the full list of filter options.

Output:

```
 Finding                                              | Tool      | Type     | Relevance
 Potential SQL injection in user input handler...     | semgrep   | sast     | 0.142
 Unparameterized query detected at api/users.py:44... | semgrep   | sast     | 0.198
 ...
```

### Chat

Ask a question about the findings using RAG-augmented LLM chat:

```
[acme-security-audit]> chat What are the most critical vulnerabilities found?
[acme-security-audit]> chat Are there any exposed admin endpoints?
[acme-security-audit]> chat Summarize the open ports and services found by nmap
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
[acme-security-audit]> stats
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
[acme-security-audit]> purge --tool=semgrep

# Delete findings from multiple tools (comma-separated)
[acme-security-audit]> purge --tool=semgrep,gitleaks

# With no flags, deletes ALL findings and clears all tool output files
[acme-security-audit]> purge
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
[acme-security-audit]> report

# HTML report — self-contained, suitable for sharing
[acme-security-audit]> report --format html

# JSON report — machine-readable, full data
[acme-security-audit]> report --format json

# Write to a specific path
[acme-security-audit]> report --output /tmp/acme-report.html --format html
```

Output:

```
✓ Report saved: projects/acme-security-audit/reports/report_2024-01-15_103422.md
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
[acme-security-audit]> project list

 Name          | Created    | Repositories | Active
 → acme-security-audit| 2024-01-14 | 2            | ✓
 corp-audit    | 2024-01-10 | 1            |

# Switch to a different project
[acme-security-audit]> project switch corp-audit
✓ Switched to project: corp-audit
[corp-audit]>

# View active project details
[corp-audit]> project info
╭─ Project: corp-audit ──────────────────────────╮
│ Created: 2024-01-10                             │
│ Repositories: 1                                 │
│                                                 │
│ Repositories:                                   │
│   • webapp (python, javascript)                 │
╰─────────────────────────────────────────────────╯
```

Each project has completely isolated findings, chat history, and reports. Switching projects does not affect the other project's data.
