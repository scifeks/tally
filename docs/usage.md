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
 semgrep            | system_tool  | ! NOT FOUND      | pip install semgrep

Warning: 1 optional tool not found. Some scan features will be unavailable.

[*] Discovering tools...
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
  Company Name: Acme Corp
  Department Name (optional):
  Abbreviation (max 3 chars, used as finding prefix e.g. FOO-001, optional): ACM
✓ Project created: acme-security-audit
[acme-security-audit]>
```

**Company Name** is required and is shown in the report's confidentiality blurb.
**Abbreviation** (optional, max 3 chars) is used as the finding ID prefix for reports generated for this project — for example, `ACM-001`. If left blank, the global `report_finding_prefix` from `config/global.json` is used instead (default: `TAL`).

The new project becomes the active project immediately. The prompt changes to show `[acme-security-audit]>`.

Project files are created under `projects/acme-security-audit/`:

```
config/
  project.json         # Project metadata
  repositories.json    # Configured repositories
  endpoints/           # Per-repo API endpoint configs
chroma_db/             # RAG vector store
tool_outputs/          # Raw tool output files
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
- **Node.js app** — shown when JavaScript or TypeScript is detected; see below
- **Dependencies file** — for Python repos, path to a dependencies file for pip-audit (optional; if omitted, pip-audit is skipped in local mode)
- **Base URLs** — API base URLs for ZAP scanning (optional, press Enter to skip)

```
[acme-security-audit]> repo add
Repository #1:
  Name: api-server
  Type: api
  Mode [local/docker] [local]:
  Local path: /home/user/projects/acme/api
  Languages (detected python) [python]:
  Note: without a dependencies file, pip-audit will be skipped for this repository.
  Python dependencies file (local path, e.g. requirements.txt, optional): requirements.txt
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
  Note: if no dependencies file is provided, pip-audit will scan all packages installed in the container environment.
  Python dependencies file (container path, e.g. /app/requirements.txt, optional): /app/requirements.txt
  Base URLs (comma-separated, optional):
✓ Repository 'api-server' added to project 'acme-security-audit'
```

### Node.js repositories and Noir

When Tally detects JavaScript or TypeScript in a repository it asks:

```
  Is this a Node.js app? (Noir will be skipped) [y/N]:
```

Answering `y` marks the repository as a Node.js app (`node_app: true` in
`repositories.json`). This causes Noir to be skipped for that repository in
all scan types. ZAP will fall back to quickscan mode for those repositories.

The reason for this flag is a known defect in Noir's JavaScript parser that
causes it to loop indefinitely on complex Node.js codebases and produce no
output. Skipping Noir avoids a silent, wasted scan step.

**Workaround (planned):** A future release will let you configure a path to a
pre-existing OAS3, OAS2/Swagger, or Postman collection file on the repository.
When set, Tally will pass it directly to ZAP, bypassing Noir entirely — which
gives Node.js apps (and any project that maintains its own API spec) the same
endpoint-guided scanning that Noir provides for other stacks.

To set or clear the `node_app` flag after a repository has been created:

```
[acme-security-audit]> repo edit api-server
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

Runs all segments (sast, sca, secrets, api) in order across all configured repositories.

```
[acme-security-audit]> scan
```

Tally prompts for approval before each tool execution:

```
Full Scan: acme-security-audit
──────────────────────────────────────────────────

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

**Run all tools of a given domain:**

Valid domains: `code`, `web`

```
[acme-security-audit]> scan --domain=code
[acme-security-audit]> scan --domain=code,web
```

**Skip specific tools:**

Run the full scan but exclude one or more tools:

```
[acme-security-audit]> scan --skip-tools=noir,zap
[acme-security-audit]> scan --skip-tools=zap
```

`--skip-tools` and `--tool` are mutually exclusive — use `--tool` to run only named tools, or `--skip-tools` to run everything except named tools.

**Scope to a single repository:**

```
[acme-security-audit]> scan --repo=api-server
```

If you have only one repository, `scan` (no flags) already targets it.

**Combine flags:**

```
[acme-security-audit]> scan --repo=api-server --tool=semgrep
[acme-security-audit]> scan --tool=semgrep --domain=code
[acme-security-audit]> scan --repo=api-server --skip-tools=zap
```

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
[acme-security-audit]> run semgrep --config auto /path/to/repo
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

Run `search --help` for the full list of filter options inline.

### Search flags

#### Core filters

| Flag | Description | Example |
|---|---|---|
| `--tool=<name,...>` | Filter by configured tool name. Comma-separated. | `--tool=semgrep` |
| `--domain=<domain,...>` | Filter by domain. Comma-separated. | `--domain=code` |
| `--type=<type,...>` | Filter by finding type. Comma-separated. | `--type=secret` |
| `--severity=<level,...>` | Filter by severity level. Comma-separated. | `--severity=high` |
| `--confidence=<level>` | Filter by confidence level. | `--confidence=confirmed` |

Valid values — `--domain`: `code`, `web`, `network`. `--type`: `secret`, `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `dependency`, `informational`. `--severity`: `critical`, `high`, `medium`, `low`, `informational`. `--confidence`: `confirmed`, `probable`, `potential`.

#### Code domain filters

| Flag | Description | Example |
|---|---|---|
| `--file~=<path>` | File path (partial match) | `--file~=src/auth` |
| `--rule=<id>` | Rule ID (exact match) | `--rule=python.lang.security.audit.exec` |

#### Web domain filters

| Flag | Description | Example |
|---|---|---|
| `--url~=<url>` | URL (partial match) | `--url~=/api/` |
| `--method=<method>` | HTTP method (exact match) | `--method=POST` |
| `--param~=<name>` | Parameter name (partial match) | `--param~=id` |
| `--alert~=<name>` | Alert name (partial match) | `--alert~=injection` |

#### Network domain filters

| Flag | Description | Example |
|---|---|---|
| `--host=<ip>` | IP address (exact match) | `--host=10.0.0.1` |
| `--host~=<pattern>` | IP address (partial match) | `--host~=10.0.0` |
| `--port=<number>` | Port number (exact match) | `--port=443` |
| `--service~=<name>` | Service name (partial match) | `--service~=ssh` |
| `--transport=<proto>` | Transport protocol (exact match) | `--transport=tcp` |

#### SCA filters

| Flag | Description | Example |
|---|---|---|
| `--vulnerability_id=<id>` | Vulnerability identifier (exact match) | `--vulnerability_id=CVE-2023-1234` |
| `--package_name=<name>` | Package name (exact match) | `--package_name=requests` |
| `--ecosystem=<name>` | Package ecosystem (exact match) | `--ecosystem=PyPI` |

#### Display and pagination

| Flag | Description | Example |
|---|---|---|
| `--fields=<f1,f2,...>` | Columns to display in results | `--fields=severity,file` |
| `--show-fields` | List available fields for a tool. Requires `--tool=<name>`. | `--show-fields` |
| `--page=<n>` | Show page N of results (default: 1) | `--page=2` |
| `--page-size=<n>` | Results per page (default: 200 for filter-only, 20 for semantic) | `--page-size=50` |

#### Match operators

Two operators are available for string filters:

- `--flag=<value>` — exact match. The stored value must equal `<value>` exactly.
- `--flag~=<value>` — contains match (SQL `LIKE`). The stored value must contain `<value>` as a substring.

Examples:

```
[acme-security-audit]> search --rule=generic-api-key
[acme-security-audit]> search --file~=config
```

The first matches only findings where the rule ID is exactly `generic-api-key`. The second matches any finding where the file path contains the string `config`.

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
[acme-security-audit]> chat Summarize the most critical vulnerabilities found
```

Tally retrieves relevant findings from the knowledge base and passes them to the Ollama LLM as context. The response appears in a panel:

```
╭─ Assistant ─────────────────────────────────────────────╮
│ Based on the scan findings, the most critical issues    │
│ are:                                                    │
│ 1. SQL injection risk at api/users.py (semgrep)         │
│ 2. Exposed admin endpoint on port 8080 (ZAP)            │
│ ...                                                     │
╰─────────────────────────────────────────────────────────╯
```

### Stats

View a summary of what has been ingested:

```
[acme-security-audit]> stats
 Metric            | Value
 Total Documents   | 42
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
# Delete findings from a specific tool (reports and other tools unaffected)
[acme-security-audit]> purge --tool=semgrep

# Delete findings from multiple tools (comma-separated)
[acme-security-audit]> purge --tool=semgrep,gitleaks

# Full purge: deletes ALL findings, tool output files, and generated reports
[acme-security-audit]> purge

# Full purge but keep generated reports
[acme-security-audit]> purge --keep-reports
```

Tally shows a count and prompts for confirmation before deleting:

```
Found 18 document(s). Delete all semgrep findings? [y/N] y
Deleted 18 document(s).
```

A full `purge` also clears the project `reports/` directory (including any LLM
drafts). Use `--keep-reports` to preserve those files. Reports can be
regenerated at any time with `report draft` and `report`.

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

---

## Deleting a Project

Delete a project and all of its data permanently:

```
[acme-security-audit]> project delete <name>
```

Tally prompts for confirmation before proceeding:

```
Delete project 'acme-security-audit' and ALL its data? [y/N]: y
Project 'acme-security-audit' deleted.
```

Deletion removes the entire `projects/<name>/` directory, including the findings database, ChromaDB store, tool outputs, and reports. This action cannot be undone.

If the deleted project was the active project, the active project is cleared. Tally prints a message prompting you to create or switch to another project:

```
Active project cleared. Use 'project add' or 'project switch' to set a new one.
```

---

## Editing Project Settings

Use `project edit` to update a project's company name, department name, or finding ID abbreviation after creation:

```
[acme-security-audit]> project edit
```

If a project name is not given and a project is active, Tally edits the active project. Pass a name explicitly to edit any project:

```
[acme-security-audit]> project edit corp-audit
```

Tally pre-fills each field with its current value. Press Enter to keep it:

```
Editing project 'acme-security-audit' (press Enter to keep current value)...

  Company Name [Acme Corp]:
  Department Name (optional) [Engineering]:
  Abbreviation [current: ACM, enter --clear to remove]:

✓ Project 'acme-security-audit' updated
```

To clear the abbreviation (reverting to the global prefix), enter `--clear` at the abbreviation prompt.
