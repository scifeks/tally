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
3. Start the FastAPI server on `https://<web_ui_host>:<web_ui_port>` in a background thread.
4. Start the Vite dev server on `https://<web_ui_host>:<web_ui_vite_port>`.
5. Wait for Vite to become reachable (polls TCP, 10-second timeout).
6. Open your default browser at the Vite URL with the session token:
   ```
   https://127.0.0.1:3000/?h=<token>
   ```

Both servers run until the REPL exits.

If the configured port is already in use, the command prints an error and does not start a server.

---

## Configuration

All web UI settings live in `config/global.json`. Copy `config/global-example.json` as a starting point with sensible defaults.

| Field | Default | Description |
|---|---|---|
| `web_ui_host` | `"127.0.0.1"` | Bind address for FastAPI and Vite. `0.0.0.0` and `::` are rejected. |
| `web_ui_port` | `8080` | FastAPI server port. |
| `web_ui_vite_port` | `3000` | Vite dev server port. |
| `web_ui_allowed_origins` | derived | CORS allow-list. Defaults to `["https://<web_ui_host>:<web_ui_vite_port>"]`. Override only for non-standard topologies. |

**Example:**

```json
{
  "web_ui_host": "127.0.0.1",
  "web_ui_port": 8080,
  "web_ui_vite_port": 3000
}
```

`web_ui_allowed_origins` can be omitted. Tally derives the correct value from `web_ui_host` and `web_ui_vite_port`.

### Host constraint

`web_ui_host` must be an explicit IP (e.g. `127.0.0.1` or a LAN address). `0.0.0.0` and `::` are rejected because the findings UI exposes real security findings that should not be reachable from other machines.

Both the FastAPI server and the Vite dev server bind to this address so session cookies work across the two ports.

---

## Projects

The top bar contains a project dropdown for switching between projects. All pages in the UI are scoped to the selected project.

### Creating a project

Click the "+ new project" button in the project dropdown to open the project creation dialog. Fill in:

1. **Project name** (required). Must start with a letter or digit. May contain letters, digits, spaces, and hyphens.
2. **Company name.** Shown in report headers and the confidentiality blurb.
3. **Department name** (optional).
4. **Abbreviation** (optional, max 3 characters). Used as the finding ID prefix in reports (e.g. `ACM-001`). When blank, the global `report_finding_prefix` from `config/global.json` is used.

Click "Create" to initialize the project. Tally creates the project directory structure, initializes the findings database, and switches to the new project automatically.

To set up credential encryption for the new project, use the REPL command `project key setup`. See [docs/configuration.md](configuration.md#encryption-and-key-management) for details.

---

## Dashboard

The dashboard (`/`) is the entry point when you launch the UI. It displays a summary of the active project and quick-action tiles.

**Project header** shows the project code and name, followed by four key metrics: repository count, URL list count, enabled tools, and scan count.

**Quick actions** are tiles linking to the main workflows: new scan, repositories, URL lists, tool config, and findings review.

**Recent scans** table lists your last scan runs with ID, domains scanned, status, start time, duration, and tool run count.

**Quick stats** show the date of the last scan, total findings, open critical/high severity issues, and the 10 most recent high-severity active findings.

---

## Findings

The Findings page (`/findings`) displays all discovered security issues in a searchable, filterable table.

Each finding row shows: ID, tool, severity (color-coded), confidence, finding type, file path, rule or alert name, description, URL, status, report inclusion flag, title, remediation guidance, and CWE.

### Filtering and searching

Use the filter header to narrow findings by severity, status, and tool. Enter text in the search box to filter by description or title. Click column headers to sort; clicking again toggles direction.

### Inline editing

Click any editable cell to modify it in place. Press Enter to save or Escape to cancel. Editable fields include: severity, confidence, finding type, description, status, report inclusion, business impact, TAL ID, CWE, title, remediation, and OWASP category.

Read-only fields (ID, tool, file, rule, URL, first-seen date) cannot be edited.

> **Note:** Running a new scan overwrites scanner-provided fields (severity, confidence, description, CWE) with fresh values. Analyst edits to those fields are not preserved across re-scans. Fields that scanners do not produce (title, remediation, business impact, status) are preserved.

### Adding manual findings

Click the plus button above the findings table to add a finding discovered outside the scanning pipeline. Title and severity are required. You must provide at least one location (repository, file path, or URL).

---

## Scans

The Scans page (`/scans`) is where you configure and launch security assessments across selected repositories and tools.

### Basic scan

Click the Play button at the top left to start a scan with the default configuration (all repos, all tools, all segments).

A real-time progress panel appears, showing elapsed time, enrichment progress, and a log of scan events. The radar visualization animates while the scan runs.

### Advanced options

Click "Advanced options" to customize the scan:

- **Repositories**: Select specific repos to scan. Leave unselected to scan all.
- **Domains**: Check SAST, SCA, WEB, or SECRETS to enable only those segment types.
- **Tools**: Select specific tools to run. Leave unselected to use all enabled tools.
- **Skip tools**: Disable specific tools within the selected set.
- **Skip enrichment**: Skip the LLM enrichment step during finding ingest. Findings are stored without AI-generated severity, remediation, and description fields.
- **Argument profiles**: Apply custom argument profiles you created on the Configuration page. Profiles override the default arguments for specific tools.

### Saved scans

The "Saved scans" tab displays scan configurations you have saved for reuse. Click a saved scan to load its options, then click Play to run it.

Create a new saved scan by configuring advanced options and clicking "Save scan". Delete a saved scan from the dropdown menu.

### Tool run history

After a scan completes, the page shows detailed timing and status for each tool run grouped by domain (SAST, SCA, WEB, SECRETS). Expand each tool group to see per-repo or per-host timing information.

### Burp scan

When Burp Suite is configured and reachable, an orange **Start Burp Scan** button appears next to the green **Start Scan** button. To its right, a tag input field accepts optional scan configuration names. Each name becomes a removable chip.

Click the button to start a crawl-and-audit scan against all base URLs in the active project. If you entered configuration names, Burp uses those profiles instead of its defaults. Multiple names are merged (useful for combining a crawl config with an audit config). If no names are entered, Burp runs with all checks enabled.

Scan progress appears in the live log. The count shown during the scan is the raw event count, not the final ingested count. When Burp reports the scan as succeeded, Tally ingests all findings in one batch.

See [docs/burp.md](burp.md) for Burp setup, scan configurations, and the Organizer polling workflow.

### Poll Burp

When `burp.mcp_url` is configured in `config/global.json`, an orange **Poll Burp** button appears on the Scans page. Clicking it starts a polling loop that fetches items from Burp's Organizer and ingests them as findings. While active, the button changes to **Stop Polling**.

Ingested findings appear on the Findings page under the `web` segment with tool `burp_organizer`. If an LLM provider is configured for the `enrichment` role, developer notes on Organizer items are classified into vulnerability type, CWE, and severity. See [docs/burp.md](burp.md) for Organizer polling setup.

---

## Triage

The Triage page (`/triage`) uses an AI agent to analyze findings. The agent reads each finding and its source code, then produces a verdict with severity, confidence, remediation, and attack vector. Two backends are supported: Claude Code (Anthropic API) and OpenCode (local Ollama). See [docs/triage.md](triage.md) for backend setup and the container security model.

### Starting triage

Click "Start triage" to launch the agent against untriaged findings in the active project. The page shows how many findings are eligible.

Triage requires Docker and a configured `triage_inference` block in `config/global.json`. If prerequisites are not met, the button is disabled with a message explaining what is missing.

### Real-time progress

As triage runs, the page displays overall progress (findings processed / total eligible), a batch list grouped by segment with status and timing, a live event log, and an elapsed time counter.

### Batch visualization

Expand a batch to see the AI-generated content. Each batch groups related findings (by segment, rule, or file) to give the agent context. Batches show status: pending, running, succeeded, or failed. Failed batches can be retried manually.

### Prompt injection warning

A warning banner appears when you launch triage, reminding you that source files and finding metadata are sent to the configured LLM. Repository content may contain adversarial input. See [docs/triage.md](triage.md) for the full security model.

### Resume from failure

If a triage run fails mid-way, the page shows a resume option. Click "Resume triage" to restart from the failure point without re-processing completed batches.

---

## Reports

The Reports page (`/reports`) generates security assessment reports in PDF, JSON, or HTML formats.

### Report generation

Select a format from the dropdown, choose the testing type (`white_box`, `grey_box`, or `black_box`), and click "Generate report". The page shows a pre-flight checklist of your project name, findings count, and recent scans.

### Draft sections

You can generate individual draft sections (executive summary, risk level, critical issues, improvement points, scope and methodology, general recommendations) without assembling a full report. Each section appears as a card with the AI-generated content, word count, and a preview pane. Edit any section by clicking the edit icon and re-generating. See [docs/report.md](report.md) for the full PDF assembly workflow.

### Report history

A table below the generation section lists all previously generated reports with format, filename, file size, creation time, and a download link.

---

## Chat

The Chat page (`/chat`) provides a multi-turn conversation interface scoped to your active project.

### Sessions

The left panel shows chat sessions. Click a session to load its history. Create a new session with the plus button. Each session is project-scoped and isolated from other projects.

### Messages

Type in the input box and press Enter or click Send. Responses stream in real time and are grounded in the active project's findings via RAG retrieval. Delete a session with the trash icon; deleted sessions and their messages are removed permanently.

---

## Project Configuration

The Configuration page (`/config`) is the most feature-rich page in the app. It manages project metadata, repositories, endpoint files, auth credentials, tool execution overrides, and custom argument profiles. The page uses a two-column layout: repositories on the left, tool overrides on the right.

### Project information

View and edit the project name and metadata at the top of the left column.

### Repositories

Repositories define what Tally scans. Each repository points to a codebase on disk (or in a Docker container) and carries configuration for languages, scan targets, dependencies, endpoint files, and auth credentials.

#### Basic mode

Basic mode treats a repository as a single unit. Click "Add repository" and fill in:

1. **Repository name.** A short identifier used in scan output (e.g. `api-server`).
2. **Repository path.** The absolute filesystem path to the code on your machine.
3. **Type.** Select `library`, `api`, `ui`, or a combination. `library` is mutually exclusive with `api` and `ui`. Type controls which scan segments apply.
4. **Location mode.** Toggle between `local` (code lives on the host filesystem) and `docker` (code is mounted inside a running container).
   - **Local:** No additional fields. Scanners access code via the repository path.
   - **Docker:** Two additional fields appear: **Container Name** (the `docker ps` name of a running container) and **Mount Point** (the path inside the container where the code is mounted, e.g. `/app`).
5. **Languages.** Tag the programming languages used (e.g. `python`, `javascript`, `php`). This controls which SCA tools run: `python` selects pip-audit, `javascript`/`typescript` select npm-audit, `php` selects composer-audit.
6. **Base URLs.** One or more URLs where the application is running (e.g. `http://localhost:8080`). DAST tools (ZAP, Nuclei, XSStrike, DalFox, sqlmap) scan these. Leave empty to skip web scanning.
7. **Test directories.** Directory names (e.g. `tests`, `spec`, `__tests__`) excluded from SAST and secrets results. Matched by name at any depth, case-insensitive.
8. **Ignore directories.** Directory names (e.g. `vendor`, `node_modules`) excluded from all scans.

Click Save to create the repository. To edit, click the pencil icon. To delete, click the trash icon.

#### Crawler settings

When base URLs are configured, crawler settings appear:

- **Enable live crawling.** Turns on the Katana web crawler, which spiders your application and discovers endpoints at scan time.
- **Katana headless mode.** Uses Chrome to render JavaScript routes. Required for single-page applications. Automatically caps crawl depth at 5 to prevent stalls on cyclic apps.
- **Crawl depth.** How many link levels deep to crawl (1-20 in standard mode, 1-5 in headless mode).

#### Dependencies file

Set the path to a dependency manifest so SCA tools can scope their scan. For local repositories, use a path relative to the repo root (e.g. `requirements.txt`). For Docker repositories, use the container-internal path (e.g. `/app/requirements.txt`).

When no dependencies file is set, pip-audit is skipped for local repositories. Docker repositories fall back to scanning all installed packages in the container.

#### Endpoint file

Upload an API specification or capture file to provide DAST tools with a pre-built list of endpoints. Accepted formats: OpenAPI 3.x, Swagger 2.0, Postman collections, HAR (HTTP Archive), and Katana JSONL output. The format is auto-detected.

When an endpoint file is uploaded and base URLs are configured, a checkbox appears: **"Also run live crawlers to supplement the endpoint file?"** When unchecked, ZAP and other DAST tools rely entirely on the endpoint file. When checked, Tally also runs Katana and Noir to discover additional endpoints. Both sources are merged and deduplicated before scanning.

Uploading a new file replaces the previous one. See [docs/endpoint-files.md](endpoint-files.md) for format details and [docs/url-discovery.md](url-discovery.md) for how endpoint files interact with the URL discovery pipeline.

#### Garak LLM config

Upload a YAML configuration file for the Garak LLM vulnerability scanner. The file specifies the target model, probes to run, and connection settings. One config file per repository. When no garak config is present, garak is skipped for that repository. See [docs/tools.md](tools.md#garak-llm-scanner) for the config format.

#### Auth credentials

Configure authentication at the bottom of each repository form. Two strategies are available: form-based login and header-based injection. Select the strategy using the auth type toggle.

**Form-based login.** Tally performs a pre-scan login by POSTing to a login form, extracts the session cookie, and injects it into crawlers and DAST tools. Set:

- **Login URL.** The login form endpoint (e.g. `https://example.com/login`).
- **Username** and **Password.** Credentials for form-based login.

**Header-based auth.** Tally injects custom HTTP headers into all crawler and DAST tool requests. Use this for bearer tokens, API keys, or any header-based authentication scheme. Each header entry has:

- **Header name.** The HTTP header (e.g. `Authorization`, `X-API-Key`).
- **Value.** An inline value, encrypted at rest.
- **Environment variable.** An environment variable containing the value at runtime. When set, the environment variable takes precedence over the inline value.

Click "+ Add Header" to add entries. Click the remove button on a row to delete it.

**Saving and security.** Click "Save Auth" to persist credentials independently from the main repository save. Credentials are encrypted at rest using the project's encryption key. The server never echoes credential values back: the API returns sentinel placeholders (`********`) for stored header values and "Stored" for form passwords. Enter new values to replace existing credentials, or leave fields unchanged to keep them.

See [docs/configuration.md](configuration.md#authentication-optional) for the JSON field reference and [docs/configuration.md](configuration.md#encryption-and-key-management) for key setup.

#### Advanced mode (multi-service)

For monorepos or applications with multiple logical services that need different scan settings, switch to Advanced mode. Click "Switch to Advanced" at the top of the repository form. The interface changes to show a service list on the left side of the repository panel.

Each service within the repository gets its own:

- **Service name** (e.g. `backend`, `frontend`, `auth-service`)
- **Relative path** within the repository root (e.g. `packages/api`)
- **Type, location mode, languages, base URLs, test/ignore directories, dependencies file, and crawler settings** (same fields as basic mode, but per-service)

Click "Add Service" to create additional services. Click a service name to select and edit it. Delete a service with the trash icon (disabled when only one service remains).

Switching to advanced mode is one-way when multiple services exist. You can only switch back to basic mode if you reduce to a single service named "default".

### Tool overrides

The right column of the Configuration page controls how individual tools execute for this project. By default, tools use the global configuration from `config/commands.json`. Project-level overrides let you change how a specific tool runs without affecting other projects.

#### Adding an override

Click "Add Override" and select a tool from the dropdown. For each override, configure:

**Type.** Toggle between `repo` (repository-scoped tools like Semgrep, Gitleaks, pip-audit) and `api` (network-scoped tools like ZAP, Nuclei, sqlmap). This controls whether the tool receives a repository path or a target URL.

**Location.** Toggle between `local` and `docker`:

- **Local:** Provide the absolute path to the tool binary on the host (e.g. `/usr/local/bin/semgrep`).
- **Docker:** Provide the container name and the path to the tool binary inside the container (e.g. container `semgrep-container`, tool path `/usr/local/bin/semgrep`). Some tools do not support Docker execution; the Docker option is disabled for those tools.

**Args.** Toggle between `stock` and `custom`:

- **Stock:** The tool runs with its default arguments. No additional configuration needed.
- **Custom:** An argument template editor appears where you build named argument profiles.

#### Argument profiles

When args mode is set to `custom`, you can create one or more named argument templates (profiles). Each profile is a named set of command-line flags and values that override the tool's defaults at scan time.

Click "Add Template" to create a new profile. Give it a descriptive name (e.g. `aggressive-scan`, `quick-check`, `with-custom-wordlist`). Then add arguments:

Each argument has:
- **Argument name.** The flag (e.g. `--wordlist`, `-v`, `--severity-threshold`).
- **Operator.** `=` (value joined with equals sign) or space (value as separate argument).
- **Type.** `None` for boolean flags that take no value, `String` for text values, or `File` for file uploads. File arguments are uploaded and stored with the profile.
- **Value.** The argument value (for String and File types).

Add as many arguments as needed per profile. Create multiple profiles for different scan scenarios. When you launch a scan on the Scans page, the "Argument profiles" advanced option lets you select which profile to apply.

Click "Done" to close the editor. Profiles are saved when you save the tool override. Click the trash icon to delete a profile.

#### Editing and removing overrides

Select an existing override from the dropdown to edit it. Click "Remove Override" to delete it and revert to the global configuration for that tool.

---

## URL Lists

The URL Lists page (`/urls`) shows a unified inventory of all endpoints known to Tally for the active project. This is a read-only view. URLs come from three sources:

1. **Endpoint files** uploaded on the Configuration page (OpenAPI, Swagger, Postman, HAR, Katana JSONL).
2. **Katana crawls** that discover endpoints by spidering your running application during scans.
3. **Noir analysis** that discovers endpoints by statically analyzing your source code during scans.

URLs from all sources are merged and deduplicated. Identical endpoints discovered by multiple tools or files appear once. When both Noir and Katana discover the same path, Noir's query parameter metadata is merged into the Katana entry.

### What the table shows

Each row represents a discovered endpoint with columns for HTTP method (color-coded), protocol (http/https), host, port, path, and source repository. The table uses virtual scrolling to handle thousands of URLs.

### Filtering and sorting

Filter by any column dimension: HTTP method, protocol, host, port, path, or repository. Each filter dropdown shows available values with counts. Multiple filters combine to narrow results.

Enter text in the search box to search across path, method, host, and repository name.

Click any column header to sort. Click again to toggle direction. Click a third time to clear the sort.

### How URL lists are consumed

Before each DAST tool runs, Tally rebuilds two merged artifacts from the URL inventory:

- **`merged_urls.txt`**: A deduplicated list of URLs, one per line. Used by XSStrike, DalFox, and Nuclei as seed URLs.
- **`merged_oas3.json`**: An OpenAPI 3.0 document combining all discovered paths and methods. Used by ZAP via its `-openapifile` flag for targeted API scanning.

You do not need to manage these files. Tally generates them automatically before each scan from whatever URLs exist in the inventory at that point.

---

## Security Model

When `ui serve` runs, Tally generates a one-time session token. The full URL including the token is opened in your browser. After the SPA loads, the token is exchanged for session cookies and removed from the address bar. The handshake URL is single-use; a second visit after the exchange receives a 401.

The server binds to `web_ui_host` only (default `127.0.0.1`). It is not accessible from other machines on the network.

CORS is enabled for the Vite origin only. Wildcard (`*`) is never used.
