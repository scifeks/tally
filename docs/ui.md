# Tally Web UI

## Overview

The Tally Web UI is a browser-based security auditing platform launched on demand from the REPL via `ui serve`. It starts a FastAPI server, a Vite dev server, and opens a browser tab pointed at the React SPA.

The UI is a full-featured multi-project application for configuring scans, running active security assessments, triaging findings with AI, generating compliance reports, and collaborating on vulnerability remediation. No active REPL project is required. You select a project from a dropdown menu upon startup.

---

## Prerequisites

### Frontend build

The React SPA must be installed before first use:

```bash
bash install.sh
```

`install.sh` runs `npm install` inside `ui/`. Node.js and npm must be present. If either is missing, `install.sh` prints an error and stops.

`ui serve` starts Vite's development server at runtime. It does not require a pre-compiled build.

---

## Starting the UI

From inside the Tally REPL (no active project required):

```
[no-project]> ui serve
```

Tally will:

1. Generate a one-time session token.
2. Write `ui/.env.local` with the configured host, ports, and API base URL.
3. Start the FastAPI server on `http://<web_ui_host>:<web_ui_port>` in a background thread.
4. Start the Vite dev server on `http://<web_ui_host>:<web_ui_vite_port>`.
5. Wait for Vite to become reachable (polls TCP, 10-second timeout).
6. Open your default browser at the Vite URL with the session token:
   ```
   http://127.0.0.1:3000/?token=<token>&fresh=1
   ```

Both servers run until you press Ctrl+C or the REPL exits.

If the configured port is already in use, the command prints an error and does not start a server.

---

## Configuration

All web UI settings live in `config/global.json`. Copy `config/global-example.json` as a starting point with sensible defaults.

| Field | Default | Description |
|---|---|---|
| `web_ui_host` | `"127.0.0.1"` | Bind address for FastAPI and Vite. `0.0.0.0` and `::` are rejected. |
| `web_ui_port` | `8080` | FastAPI server port. |
| `web_ui_vite_port` | `3000` | Vite dev server port. |

**Example:**

```json
{
  "web_ui_host": "127.0.0.1",
  "web_ui_port": 8080,
  "web_ui_vite_port": 3000
}
```

CORS origins are derived automatically from `web_ui_host` and `web_ui_vite_port`. No manual CORS configuration is needed.

### Host constraint

`web_ui_host` controls both the FastAPI bind address and the Vite bind address. Tally writes `ui/.env.local` before starting Vite so both servers always share the same hostname. This is required for `SameSite=Strict` session cookies to work across the two ports. Cookies are scoped to a registrable domain, not an origin, so they flow cross-port when the hostname matches.

`0.0.0.0` and `::` are rejected at config load with a clear error message. Running the findings UI on a network-visible address would expose real security findings to other machines.

---

## Dashboard

The dashboard (`/`) is the entry point when you launch the UI. It displays a summary of the active project and quick-action tiles.

**Project header** shows the project code and name, followed by four key metrics: repository count, URL list count, enabled tools, and scan count.

**Quick actions** are tiles linking to the main workflows: new scan, repositories, URL lists, tool config, and findings review.

**Recent scans** table lists your last scan runs with ID, domains scanned, status, start time, duration, and tool run count.

**Quick stats** show the date of the last scan, total findings, open critical/high severity issues, and the 10 most recent high-severity active findings.

---

## Findings

The Findings page (`/findings`) displays all discovered security issues from scanners in a searchable, filterable table.

Each finding row shows: ID, tool, severity (color-coded), confidence level, finding type, file path, rule or alert name, description, URL, status, whether it will be included in reports, title, remediation guidance, and CWE.

### Filtering and searching

Use the filter header to narrow findings by severity, status, and tool. You can filter by any of: `critical`, `high`, `medium`, `low`, `informational` for severity; `active`, `false_positive`, `fixed`, `wont_fix` for status; and any scanner name (Semgrep, Gitleaks, ZAP, npm-audit, etc.) for tool.

Enter text in the search box to filter by finding description or title.

Click column headers to sort by severity, title, tool, status, or first-seen date. Sorting direction toggles with repeated clicks.

### Inline editing

Click any cell in a writable column to edit. Press Enter to save or Escape to cancel.

Editable columns are listed below. After each edit, the change is written to SQLite and synced to ChromaDB.

#### Named fields

| Field | Type | Values |
|---|---|---|
| `severity` | Enum | `critical`, `high`, `medium`, `low`, `informational` |
| `confidence` | Enum | `confirmed`, `probable`, `potential` |
| `finding_type` | Array | `secret`, `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `dependency`, `informational` |
| `description` | Text | Free text |
| `status` | Enum | `active`, `false_positive`, `fixed`, `wont_fix` |
| `should_report` | Boolean | Include in generated reports |
| `business_impact` | Text | Free text |
| `tal_id` | Text | Free text identifier |
| `cwe` | Array | JSON array of CWE numbers or names |

#### Meta fields

| Field | Type | Values |
|---|---|---|
| `title` | Text | Finding title or summary |
| `remediation` | Text | Fix guidance or mitigation steps |
| `owasp_name` | Text | Valid OWASP category or null |

Read-only columns (locked from editing): ID, tool, file, rule_id, url, first_seen.

### Write safety

Edits set `triaged_by = 'analyst_web'` and record a `triaged_at` timestamp. Only the editable fields listed above are written. Locked fields including `tool`, `domain`, `fingerprint`, and raw scanner metadata are never touched.

> **Important:** If you run a new scan after editing findings, the ingest pipeline will overwrite `severity`, `confidence`, `description`, `cwe`, and `meta` with values reported by the scanner. Analyst edits to these fields are not preserved.

### Adding manual findings

Click the plus button above the findings table to add a finding that was discovered outside the scanning pipeline. A modal opens with a form to enter finding details.

Title and severity are required. You must provide at least one location field (repository, file path, or URL) to anchor the finding to a scope.

#### Fields

| Field | Required | Description |
|---|---|---|
| Title | Yes | Finding title or summary |
| Severity | Yes | `critical`, `high`, `medium`, `low`, `informational` |
| Status | No | `active`, `false_positive`, `fixed`, `wont_fix` (defaults to `active`) |
| Confidence | No | `confirmed`, `probable`, `potential` |
| Segment | No | `SAST`, `SCA`, `WEB`, `SECRETS` (populated from active project) |
| Finding Type | No | `secret`, `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `dependency`, `informational` |
| Repository | No | Scan target repository (at least one location required) |
| File | No | File path within the repository (at least one location required) |
| URL | No | Web address (at least one location required) |
| CWE | No | Comma or newline-separated CWE identifiers (e.g., CWE-79, CWE-20) |
| Vulnerability ID | No | CVE, GHSA, or other identifier |
| Description | No | Detailed explanation of the finding |
| Notes | No | Internal notes not shared in reports |

---

## Scans

The Scans page (`/scans`) is where you configure and launch security assessments across selected repositories and tools.

### Basic scan

Click the Play button at the top left to start a scan with the default configuration (all repos, all tools, all segments).

A real-time progress panel appears, showing elapsed time, enrichment progress, and a log of scan events (tool invocation, file processing, enrichment steps). The radar visualization animates while the scan runs.

When the scan completes, it appears in the recent scans table on the dashboard.

### Advanced options

Click "Advanced options" to customize the scan:

- **Repositories**: Select specific repos to scan. Leave unselected to scan all.
- **Domains**: Check SAST, SCA, WEB, or SECRETS to enable only those segment types.
- **Tools**: Select specific tools to run. Leave unselected to use all enabled tools.
- **Skip tools**: Disable specific tools within the selected set.
- **Skip enrichment**: Skip the LLM enrichment step during finding ingest. Findings are stored without AI-generated severity, remediation, and description fields.
- **Argument profiles**: Apply saved tool argument overrides (see Configuration page).

### Saved scans

The "Saved scans" tab displays scan configurations you have saved for reuse. Click a saved scan to load its options, then click Play to run it.

Create a new saved scan by configuring advanced options and clicking "Save scan". Delete a saved scan from the dropdown menu.

### Tool run history

After a scan completes, the page shows detailed timing and status for each tool run (SAST, SCA, WEB, SECRETS). Expand each tool group to see per-repo or per-host timing information.

---

## Triage

The Triage page (`/triage`) uses an AI agent to analyze SAST and API findings. The agent reads each finding and its source code, then produces a verdict with severity, confidence, remediation, and attack vector. Two backends are supported: Claude Code (Anthropic API) and OpenCode (local Ollama). See [docs/triage.md](triage.md) for backend setup and the container security model.

### Starting triage

Click "Start triage" to launch the agent against untriaged findings in the active project. The page shows how many findings are eligible.

Triage requires Docker and a configured `triage_inference` block in `config/global.json`. If prerequisites are not met, the button is disabled with a message explaining what is missing.

### Real-time progress

As triage runs, the page displays:

- Overall progress: findings processed / total findings eligible
- Batch list: grouped by segment (SAST, SCA, WEB, SECRETS) with status, attempt count, and timing for each batch
- Live log: detailed events as each batch is sent to the agent, receives responses, and persists results
- Elapsed time counter

### Batch visualization

Expand a batch in the list to see the AI-generated content. Each batch groups related findings (by segment, rule, or file) to provide context to the agent.

Batches can have status: pending, running, succeeded, failed. Failed batches can be retried manually.

### Prompt injection warning

A warning banner appears when you launch triage, reminding you that source files and finding metadata are sent to the configured LLM. This is a security reminder that repository content may contain adversarial input. See [docs/triage.md](triage.md) for the full security model.

### Resume from failure

If a triage run fails mid-way, the page shows a resume option with the failed finding ID. Click "Resume triage" to restart processing from that point, without re-processing already-completed batches.

---

## Reports

The Reports page (`/reports`) generates compliance and security assessment reports in PDF, JSON, or HTML formats.

### Report generation

Select a report format from the dropdown (PDF, JSON, or HTML), choose the testing type (`white_box`, `grey_box`, or `black_box`), and click "Generate report" to start.

The page shows a pre-flight checklist: verify your project name, findings count, and recent scans are correct before generating.

### Draft sections

You can generate individual draft sections (executive-summary, risk-level, critical-issues, improvement-points, scope-and-methodology, general-recommendations) without assembling a full report. This lets you preview content and save drafts for review. See [docs/report.md](report.md) for the full PDF assembly workflow.

When you generate drafts, each section appears as a card showing the AI-generated content, word count, and a preview pane. Edit any section by clicking the edit icon and re-generating.

### Report history

A table below the generation section lists all previously generated reports, with format, filename, file size, creation time, and a download link.

Reports are stored in the project's `reports/` directory on disk.

### Download

When a report finishes generating, its status changes to "done" and a download link appears. Click the link to save the file to your local machine.

---

## Chat

The Chat page (`/chat`) provides a multi-turn conversation interface scoped to your active project.

### Sessions

The left panel shows a list of chat sessions. Click a session to load its message history. Create a new session with the plus button at the top.

Each session is isolated and stores messages specific to that project. Switching projects clears all session history, as chats are project-scoped.

### Messages

Send a message by typing in the input box at the bottom and clicking Send or pressing Enter. The response streams in real time and is automatically added to the session history. Answers are grounded in the active project's findings via RAG retrieval from ChromaDB.

### Session management

Delete a session by clicking the trash icon next to the session name. Deleted sessions and their message history are removed permanently.

---

## Project Configuration

The Configuration page (`/config`) is where you manage project metadata, repositories, tool settings, and argument profiles.

### Project information

View and edit the project name, description, and other metadata. Changes are saved immediately.

### Repositories

#### Basic mode

Click "Add repository" to create a repository entry. Provide the repository name, type, and local path. If you need to configure multiple services (different parts of a monorepo or multi-tenant codebase), switch to Advanced mode instead.

1. Fill in the repository name.
2. Select type: library, api, ui, or a combination.
3. Set location mode: local (path on disk) or docker (container name and mount point).
4. Specify languages used in the repository.
5. Set base URLs for live crawling (DAST tools).
6. Click Save.

To edit an existing repository, click the pencil icon. To remove, click the trash icon.

#### Advanced mode

In Advanced mode, you can define multiple named services within a single repository. Each service has its own configuration for type, location mode, languages, base URLs, and crawling settings. This is useful for monorepos, multi-tenant applications, or any codebase with distinct logical services that need different scan settings.

Click "Switch to Advanced" from Basic mode. The interface changes to show a service list on the left. Click "Add Service" to create a new named service within the repository.

Each service has three groups of configuration fields.

#### Location and type

| Field | Required | Description |
|---|---|---|
| Service Name | Yes | Identifier for this service within the repository (e.g., `backend`, `frontend`, `auth-service`) |
| Relative Path | No | Sub-path within the repository root (e.g., `packages/api`, `services/web`) |
| Type | Yes | `library`, `api`, `ui`, or a combination (library cannot be combined with api or ui) |
| Location Mode | No | `local` (path on disk) or `docker` (container-mounted code) |
| Container Name | Required if docker mode | Docker container name where the code is mounted |
| Mount Point | Required if docker mode | Path inside the container where the code is mounted (e.g., `/app`) |

#### Code context

| Field | Required | Description |
|---|---|---|
| Languages | Yes | Languages used in this service (e.g., python, javascript, go). Used by scanners to select rules. |
| Test Directories | No | Directories to exclude from scanning (e.g., `tests`, `spec`, `__tests__`) |
| Ignore Directories | No | Directories to skip entirely (e.g., `vendor`, `node_modules`, `.git`) |

#### Scanning targets

| Field | Required | Description |
|---|---|---|
| Base URLs | No | Base URLs for DAST tools to scan this service (e.g., `https://api.example.com`). First URL is used as the canonical scope. |
| Dependencies File | No | Path to dependency manifest for SCA scanning (e.g., `requirements.txt`, `package.json`, `go.sum`) |
| Enable live crawling | No | Enable the Katana web crawler for this service |
| Crawl Depth | No | How many levels deep to crawl (1-20 for standard, max 5 if headless mode is enabled) |
| Katana headless mode | No | Use Chrome to render JavaScript routes (required for single-page applications, max crawl depth 5) |

### Tool overrides

Enable or disable individual scanners. For each enabled tool, you can override:

- **Container image**: Use a different Docker image version or variant.
- **Mount paths**: Configure volume mounts for the scanner container.
- **Arguments**: Set custom command-line arguments or environment variables for the tool.

Create argument templates to save and reuse common configurations across scans. Templates are named bundles of tool-specific arguments.

### Tool catalog

A read-only browser shows all tools Tally supports, grouped by category (SAST, SCA, Web, Secrets, Dependency Management). Each tool entry lists the default command and available arguments.

---

## URL Lists

The URL Lists page (`/urls`) manages target lists for web-based scanners (ZAP, custom HTTP tools).

Create a new list by clicking "New list" and pasting or uploading a file of URLs (newline-separated). Tally parses each URL and displays them in a table.

Filter URLs by HTTP method (GET, POST, PUT, DELETE, etc.), protocol (HTTP, HTTPS), hostname, port, path, and source repository.

Search for URLs by hostname, path, or query string.

Sort the table by any column. The table uses virtual scrolling for fast rendering of large lists.

---

## Security Model

When `ui serve` runs, Tally generates a one-time session token using `secrets.token_hex(16)`. The token is valid for the lifetime of the server process and is never written to disk or stored in the database.

The full URL including the token is opened in your browser directly. After the SPA loads, the token is exchanged for session cookies and removed from the address bar. Closing the tab or refreshing the page after the exchange does not require the original URL.

Every request to the FastAPI server must be authenticated via session cookie. The handshake token URL is single-use. A second visit after the exchange has completed receives a 401.

The server binds to `web_ui_host` only (default `127.0.0.1`). It is not accessible from other machines on the network.

CORS is enabled for the Vite origin only (`http://<web_ui_host>:<web_ui_vite_port>`). Wildcard (`*`) is never used.
