# Burp Suite Integration

Tally integrates with Burp Suite Professional in two ways: launching REST API scans and polling the Organizer for manually sent items. Both paths ingest findings into Tally's knowledge base, where they appear on the Findings page and are eligible for DAST triage.

This guide covers setup, configuration, and usage for both workflows.

---

## Prerequisites

You need:

- **Burp Suite Professional** (or Enterprise) running on a machine reachable from Tally
- **Burp REST API** enabled in Burp's settings (used for automated scans)
- **PortSwigger MCP server extension** installed in Burp (used for Organizer polling)

The REST API and MCP server serve different purposes. You can set up one or both depending on your workflow.

---

## Setting Up the REST API

The REST API lets Tally launch crawl-and-audit scans against your target URLs directly from the web UI or REPL.

1. Open Burp Suite Professional.
2. Go to **Settings > Suite > REST API**.
3. Check **Service running** to enable the API.
4. Note the port number (default: `1337`).
5. If Tally runs on the same machine, the default `http://127.0.0.1:1337` works. If Tally runs on a different machine, bind the REST API to an accessible interface.

See [Burp REST API settings](https://portswigger.net/burp/documentation/desktop/settings/suite/rest-api) for full details on API keys and network binding.

> **Note:** PortSwigger recommends binding the REST API to loopback interfaces only. If you expose it on a network interface, configure an API key for authentication.

---

## Installing the Burp MCP Server

The PortSwigger MCP server extension lets Tally poll Burp's Organizer for items you send during manual testing. It runs on port `9876` by default.

1. In Burp Suite, go to **Extensions > BApp Store**.
2. Search for "MCP Server" and install it.
3. The extension starts automatically. Verify it is running in the **Extensions > Installed** tab.

The extension's source and documentation are at [github.com/PortSwigger/mcp-server](https://github.com/PortSwigger/mcp-server). The BApp Store page is at [portswigger.net/bappstore/9952290f04ed4f628e624d0aa9dccebc](https://portswigger.net/bappstore/9952290f04ed4f628e624d0aa9dccebc).

---

## Adding the MCP Server to Your Coding Agent

If you use a coding agent (Claude Code, Cursor, Windsurf, or similar), you can connect it to Burp's MCP server for direct interaction with Burp's proxy history, Repeater, and Intruder.

Add the Burp MCP server to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "burp": {
      "type": "sse",
      "url": "http://127.0.0.1:9876/sse"
    }
  }
}
```

If Burp runs on a different port, update the URL to match. You can also add this to your coding agent's user-level MCP settings for global availability across all projects.

This is independent of Tally's configuration. Tally connects to the same MCP server separately for Organizer polling (configured in `config/global.json` as described below).

---

## Configuring Tally

Add a `burp` section to `config/global.json` with the fields your workflow requires.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `base_url` | string | No | `http://localhost:1337` | Burp REST API base URL. Used for automated scans. |
| `api_key` | string | No | `""` | API key for authenticated REST API access (Enterprise or when configured). |
| `mcp_url` | string | No | `""` | Root URL of Burp's MCP server (e.g., `http://127.0.0.1:9876/`). Used for Organizer polling. |
| `poll_interval_seconds` | integer | No | `30` | Seconds between Organizer poll cycles. Minimum 5. |

### Example: REST API only

```json
{
  "burp": {
    "base_url": "http://127.0.0.1:1337"
  }
}
```

### Example: REST API and Organizer polling

```json
{
  "burp": {
    "base_url": "http://127.0.0.1:1337",
    "mcp_url": "http://127.0.0.1:9876/",
    "poll_interval_seconds": 30
  }
}
```

### Example: Enterprise with API key

```json
{
  "burp": {
    "base_url": "http://10.1.20.101:1337",
    "api_key": "your-enterprise-api-key"
  }
}
```

At startup, Tally probes `GET /v0.1/` on the configured `base_url`. If the probe succeeds, Burp appears in the available tools list on the Scans page. If the probe fails, Burp is marked as configured but offline. If no `burp` section exists, Burp does not appear.

> **Note:** Burp's MCP server truncates each Organizer item to 5000 characters total. Long HTTP responses may appear incomplete. REST API scan results bypass this limit and include full request/response data.

---

## Scan Configurations

Burp scan configurations are saved profiles that control how a scan runs: which checks to perform, crawl depth, speed, and audit behavior. Tally lets you reference these by name when starting a scan.

### What named configurations are

Named configurations are presets saved inside your Burp project. Each one stores a specific combination of crawl and audit settings. When you reference a configuration name in Tally, Burp loads that profile instead of using its defaults.

Burp includes several built-in configurations:

- `Crawl and audit - lightweight`
- `Audit checks - all except time-based detection methods`
- `Crawl limit - 10 minutes`

### Creating a named configuration in Burp

1. In Burp Suite, go to **New Scan**.
2. On the **Scan configuration** tab, adjust the settings (crawl depth, audit checks, speed).
3. Click the dropdown at the top (shows "Custom" by default) and select **Save scan configuration**.
4. Enter a name and save.

The name you save is the string you enter in Tally. It must match exactly, including capitalization and spacing.

See [Custom scan configurations](https://portswigger.net/burp/documentation/scanner/scan-configurations/custom-scan-configurations) in PortSwigger's documentation for detailed options.

### Multiple configurations

You can enter multiple configuration names. Burp merges them, which is useful for combining a crawl configuration with a separate audit configuration. The REST API sends them as an array:

```json
{
  "scan_configurations": [
    {"type": "NamedConfiguration", "name": "My crawl config"},
    {"type": "NamedConfiguration", "name": "My audit config"}
  ]
}
```

### Default behavior

If you start a scan without specifying any configuration names, Burp runs its default crawl-and-audit with all checks enabled.

### No listing API

There is no Burp REST API endpoint to list available named configurations. You must know the exact name from Burp's UI. If you enter a name that does not exist, Burp returns an error.

---

## Running Scans

Burp scans use the base URLs from all configured repository services in the active project. If no base URLs are configured, the scan fails with an error.

### Web UI

When Burp is configured and reachable, an orange **Start Burp Scan** button appears on the Scans page next to the green **Start Scan** button. To the right of the button, a tag input field accepts scan configuration names.

To start a scan:

1. Click **Start Burp Scan**. If you want to use named configurations, type them into the tag input field first. Each name becomes a removable chip. The field is optional.
2. Tally collects all base URLs from the active project's repositories and sends them to Burp.
3. Scan progress appears in the live log. The progress count shown during the scan is the raw event count from Burp, not the final ingested finding count.
4. When Burp reports the scan as succeeded, Tally ingests all findings in one batch. The ingested count appears in the scan summary.

### REPL

The `burp scan` command starts a scan from the terminal:

```
[myproject]> burp scan
Starting burp scan...
```

To use a named configuration:

```
[myproject]> burp scan Crawl and Audit - Balanced
Starting burp scan (Crawl and Audit - Balanced)...
```

The REPL accepts a single configuration name as an argument. When omitted, Burp uses its default configuration.

---

## Organizer Polling

Organizer polling is a separate workflow from automated scanning. During manual testing in Burp, you send interesting requests to the Organizer (right-click a request in Proxy or Repeater and select **Add to Organizer**). Tally polls the Organizer at a configured interval and ingests new items as findings.

### Web UI

When `burp.mcp_url` is configured, a **Poll Burp Organizer** button appears on the Findings page next to **+ Add Issue**. Click it to start polling. The button changes to **Stop Polling** while active, and the segment tab switches to `web`.

Ingested findings appear under the `web` segment with tool `burp_organizer`. If an LLM provider is configured for the `enrichment` role, developer notes on Organizer items are classified into vulnerability type, CWE, and severity.

### REPL

The `burp poll` command starts a blocking polling loop:

```
[myproject]> burp poll
Polling Burp Organizer every 30s... (Ctrl+C to stop)
```

The loop runs until you press Ctrl+C. While polling, send requests to the Organizer in Burp. Tally picks them up on the next poll cycle.

---

## Finding Triage

Burp findings are triaged using the DAST triage workflow, which differs from SAST triage. A dynamic scanner has already confirmed the vulnerability by sending a crafted request and observing a vulnerable response. The triage agent's task is to locate the vulnerable code path in the source tree, not to re-confirm the scanner's observation.

### How DAST triage works

The agent asks: "Where is the vulnerability in the source code that allows this endpoint to be exploited?" It traces the code from request intake to the vulnerable operation and produces a `call_stack` field showing the full vulnerability chain.

### Burp evidence format

Burp findings include richer evidence than other DAST tools:

- Alert name, severity, and confidence
- Full HTTP request and response (decoded and human-readable)
- Vulnerability fingerprint type (identifies the specific variant detected)
- Remediation guidance (vendor-provided fix recommendations)

The triage agent reads this evidence to guide its source code investigation.

### Starting triage for Burp findings

Burp findings are triaged the same way as any other finding. Use the Triage page in the web UI or the `triage` command in the REPL. Burp findings from both REST API scans and Organizer polling are eligible. DAST triage processes findings in batches of one to give the agent full context for each HTTP request/response pair.

See [docs/triage.md](triage.md) for the complete triage guide, including backend setup and the DAST verdict format.
