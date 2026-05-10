# Tally Web UI

## Overview

The Tally Web UI is a browser-based findings reviewer launched on demand from the REPL
via `ui serve`. It starts a FastAPI server, a Vite dev server, and opens a browser tab
pointed at the React SPA.

The UI gives analysts a table-based view of all ingested findings from the active
project's SQLite database. Analyst edits to writable fields are written to SQLite and
synced to ChromaDB immediately.

---

## Prerequisites

### Frontend build

The React SPA must be installed before first use:

```bash
bash install.sh
```

`install.sh` runs `npm install` inside `ui/`. Node.js and npm must be present. If
either is missing, `install.sh` prints an error and stops.

`ui serve` starts Vite's development server at runtime — it does not require a
pre-compiled build.

### Active project

`ui serve` reads findings from the active project's SQLite database. Set a project
before running the command:

```
[acme-audit]> project switch acme-audit
```

---

## Usage

From inside the Tally REPL with an active project:

```
[acme-audit]> ui serve
```

Tally will:

1. Generate a one-time session token.
2. Write `ui/.env.local` with the configured host, ports, and API base URL.
3. Start the FastAPI server on `http://<web_ui_host>:<web_ui_port>` in a background
   thread.
4. Start the Vite dev server on `http://<web_ui_host>:<web_ui_vite_port>`.
5. Wait for Vite to become reachable (polls TCP, 10-second timeout).
6. Open your default browser at the Vite URL with the session token:
   ```
   http://127.0.0.1:3000/?h=<token>
   ```

Both servers run until `ui serve --stop` is called or the REPL exits.

To stop without exiting the REPL:

```
[acme-audit]> ui serve --stop
```

If the configured port is already in use, the command prints an error and does not
start a server.

---

## Configuration

All web UI settings live in `config/global.json`. Copy `config/global-example.json` as
a starting point — it includes sensible defaults.

| Field | Default | Description |
|---|---|---|
| `web_ui_host` | `"127.0.0.1"` | Bind address for FastAPI and Vite. `0.0.0.0` and `::` are rejected. |
| `web_ui_port` | `8080` | FastAPI server port. |
| `web_ui_vite_port` | `3000` | Vite dev server port. |
| `web_ui_allowed_origins` | derived | CORS allow-list. Defaults to `["http://<web_ui_host>:<web_ui_vite_port>"]`. Override only for non-standard topologies. |

**Example (`config/global.json` fragment):**

```json
{
  "web_ui_host": "127.0.0.1",
  "web_ui_port": 8080,
  "web_ui_vite_port": 3000
}
```

`web_ui_allowed_origins` can be omitted — Tally derives the correct value from
`web_ui_host` and `web_ui_vite_port`.

### Host constraint

`web_ui_host` controls both the FastAPI bind address and the Vite bind address. Tally
writes `ui/.env.local` before starting Vite so both servers always share the same
hostname. This is required for `SameSite=Strict` session cookies to work across the two
ports — cookies are scoped to a registrable domain, not an origin, so they flow
cross-port when the hostname matches.

`0.0.0.0` and `::` are rejected at config load with a clear error message. Running the
findings UI on a network-visible address would expose real security findings to other
machines.

---

## The Two Views

The SPA has two tabs corresponding to two finding domains.

### Code & Web Findings

Displays all findings where `domain IN ('code', 'web')` — findings from Semgrep,
Gitleaks, ZAP, and all SCA tools (pip-audit, npm-audit, composer-audit, osv-scanner).

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

Editable cells are modified by clicking the cell. Saves are applied on blur or Enter;
Escape cancels the edit. All other columns are display-only.

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
| `meta.tags` | JSON array (Gitleaks findings only) |

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

## Security Model

When `ui serve` runs, Tally generates a one-time session token using
`secrets.token_hex(16)`. The token is valid for the lifetime of the server process
and is never written to disk or stored in the database.

The full URL including the token is opened in your browser directly. After the SPA
loads, the token is exchanged for session cookies and removed from the address bar.
Closing the tab or refreshing the page after the exchange does not require the original
URL.

Every request to the FastAPI server must be authenticated via session cookie. The
handshake token URL is single-use — a second visit after the exchange has completed
receives a 401.

The server binds to `web_ui_host` only (default `127.0.0.1`). It is not accessible
from other machines on the network.

CORS is enabled for the Vite origin only (`http://<web_ui_host>:<web_ui_vite_port>`).
Wildcard (`*`) is never used.
