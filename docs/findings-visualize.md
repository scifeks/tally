# Findings Visualizer

## Overview

The findings visualizer is a local browser-based findings browser launched on demand
from the REPL via `findings visualize`. It starts a short-lived FastAPI server, serves
a pre-built Vue 3 SPA, and opens a browser tab pointed at it.

The visualizer gives analysts a table-based view of all ingested findings from the
active project's SQLite database. Findings from all tools (semgrep, gitleaks, ZAP,
SCA tools) are displayed in a single **Code & Web Findings** table.

Analyst edits to writable fields are written to SQLite and synced to ChromaDB
immediately. The server runs in a background thread and stops when the REPL exits.

---

## Prerequisites

### Frontend build

The Vue SPA is compiled at install time by `install.sh`. Node.js and npm must be
installed before running `install.sh`:

```bash
bash install.sh
```

If Node.js or npm is not installed, `install.sh` will print an error and stop. The
`findings visualize` command requires the compiled build output in `web/static/` to
be present — it does not build the frontend at runtime.

### Active project

`findings visualize` reads findings from the active project's SQLite database. A
project must be set before running the command:

```
[acme-audit]> project switch acme-audit
```

---

## Usage

From inside the Tally REPL with an active project:

```
[acme-audit]> findings visualize
```

The REPL will:

1. Generate a one-time session token
2. Start the FastAPI server on `http://127.0.0.1:8080` in a background thread
3. Print the full URL including the token:
   ```
   http://localhost:8080/?token=<token>
   ```
4. Open that URL in your default browser

The server runs until the REPL exits. Press Ctrl+C at the REPL prompt to exit Tally
and stop the server.

To stop the server without exiting the REPL:

```
[acme-audit]> findings visualize --stop
```

> **Note:** `findings visualize --stop` is not yet implemented.

If the configured port is already in use, the command prints an error and does not
start a server.

---

## The Two Views

The SPA has two tabs corresponding to two finding domains.

### Code & Web Findings

Displays all findings where `domain IN ('code', 'web')` — findings from semgrep,
gitleaks, ZAP, and all SCA tools (pip-audit, npm-audit, composer-audit, osv-scanner).

| Column | Source |
|---|---|
| ID | `id` |
| Tool | `tool` |
| Severity | `severity` (editable) |
| Confidence | `confidence` (editable) |
| Type | `finding_type` (editable) |
| File | `file` |
| Rule / Alert | `rule_id` or `meta.alert_name` |
| Description | `description` (editable) |
| URL | `url` |
| Status | `status` (editable) |
| Report? | `should_report` (editable) |
| Title | `meta.title` (editable) |
| Remediation | `meta.remediation` (editable) |
| CWE | `cwe` (editable) |

---

## Editable Fields

Editable cells are modified by clicking the cell. Saves are applied on blur or
Enter; Escape cancels the edit. All other columns are display-only.

### Named columns

| Field | Constraints |
|---|---|
| `severity` | Enum: `critical`, `high`, `medium`, `low`, `informational` |
| `confidence` | Enum: `confirmed`, `probable`, `potential` |
| `finding_type` | JSON array; values: `secret`, `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `dependency`, `informational` |
| `description` | Free text |
| `status` | Enum: `active`, `false_positive`, `fixed`, `wont_fix` |
| `should_report` | Boolean |
| `business_impact` | Free text |
| `tal_id` | Free text |
| `cwe` | JSON array string |

### Meta fields

| Field | Constraints |
|---|---|
| `meta.remediation` | Free text |
| `meta.risk_type` | snake_case string |
| `meta.owasp_name` | Valid OWASP name or null |
| `meta.title` | Free text |
| `meta.tags` | JSON array (gitleaks findings only) |

`url` is read-only and is not accepted in any edit operation.

After each save, the changed fields are synced to ChromaDB. If no matching ChromaDB
document is found for a finding, the sync is skipped and a warning is logged — the
SQLite write always succeeds regardless of ChromaDB sync status.

---

## Write Safety

Analyst edits use a separate write path from the ingest pipeline. Each edit sets
`triaged_by = 'analyst_web'` and records a `triaged_at` timestamp. Only the editable
fields listed above are written — locked fields including `tool`, `domain`,
`fingerprint`, `file`, `host`, `port`, and all raw scanner metadata are never touched.

**Important:** If you run a new scan after editing findings, the ingest pipeline will
overwrite `severity`, `confidence`, `description`, `cwe`, and `meta` with the values
reported by the scanner. Analyst edits to these fields are not preserved across
subsequent pipeline runs.

---

## Configuration

The server port is read from `config/global.json`. If the key is absent, port 8080
is used.

```json
{
  "web_ui_port": 8080
}
```

---

## Security Model

When `findings visualize` runs, the REPL generates a one-time token using
`secrets.token_hex(16)`. The token is valid for the lifetime of the server process
and is never written to disk or stored in the database.

The full URL including the token is printed to the terminal. After the browser
loads the page, the token is removed from the address bar — it lives in the browser
tab's memory only. Closing the tab or refreshing the page discards the token; the
page will not reload successfully without the original URL.

Every request to the server — including API calls made by the SPA — must include
the token as `Authorization: Bearer <token>`. Requests with a missing or invalid
token receive a 401 response immediately.

The server binds to `127.0.0.1` only. It is not accessible from other machines on
the network.
