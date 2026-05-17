# DefectDojo Integration

Tally can export scan findings to a DefectDojo instance. Findings are
mapped to the DefectDojo Generic Findings Import format and pushed via
the reimport-scan API, which handles deduplication automatically on
repeated exports.

---

## Prerequisites

- A running DefectDojo instance (v2.x or later)
- An API token with permission to create findings. Generate one from
  your DefectDojo user profile under **API v2 Key**.

---

## Entity mapping

Tally maps its data model to DefectDojo's hierarchy as follows:

| Tally concept | DefectDojo entity | How it maps |
|---|---|---|
| Repo | **Product** | Each repo becomes its own Product, named `"{project} / {repo}"`. Isolates deduplication per repo. |
| Global `product_type` config | **Product Type** | Configurable label that groups Products. Default: `"Tally Scan"`. |
| Resolved `engagement_type` | **Engagement** | Configurable assessment label within each Product. Default: `"Tally Engagement"`. |
| Tool run (semgrep, zap, etc.) | **Test** | Each tool creates a separate Test within the Engagement. |
| Individual vulnerability | **Finding** | Each vulnerability becomes a Finding within the tool's Test. |

Findings without a repo association are grouped into a Product named
`"{project} / Unassociated"`.

---

## Configuration

Configuration is split across two levels. Connection settings and
defaults live in `config/global.json` (shared across all projects).
An optional project-level override in `project.json` can set a
per-project engagement type.

### Global settings

Add a `defectdojo` block to `config/global.json`:

```json
{
  "defectdojo": {
    "url": "https://defectdojo.internal.example.com",
    "api_token": "your-api-token-here",
    "verify_ssl": true,
    "product_type": "Tally Scan",
    "engagement_type": "Tally Engagement"
  }
}
```

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | | Base URL of your DefectDojo instance. Must use `http://` or `https://`. |
| `api_token` | string | Yes | | API v2 token from your DefectDojo user profile. |
| `verify_ssl` | bool | No | `true` | Verify TLS certificates. Set to `false` for self-signed certificates. |
| `product_type` | string | No | `"Tally Scan"` | Product Type label in DefectDojo. Groups all repo Products under a common type. |
| `engagement_type` | string | No | `"Tally Engagement"` | Default Engagement name. Can be overridden per project or per invocation. |
| `auto_create_context` | bool | No | `true` | Create the Product, Engagement, and Product Type in DefectDojo if they do not exist. |
| `scan_type` | string | No | `"Generic Findings Import"` | DefectDojo scan type (test type) used for the import. Controls the "Found By" label. See [Custom scan type](#custom-scan-type). |

### Project-level override (optional)

You can override `engagement_type` per project by adding a `defectdojo`
block to `projects/<name>/project.json`:

```json
{
  "project_name": "acme-audit",
  "defectdojo": {
    "engagement_type": "CI/CD"
  }
}
```

This is optional. If omitted, the global `engagement_type` is used.

### Engagement type resolution

The engagement type follows a three-tier cascade:

1. **CLI/REPL `--engagement-type` flag** (highest priority)
2. **Project config** `defectdojo.engagement_type`
3. **Global config** `defectdojo.engagement_type` (default)

---

## Usage

### Test the connection

Verify that Tally can reach your DefectDojo instance and authenticate:

```
[acme-audit]> sync --integration=defectdojo --test-connection
DefectDojo connection successful.
```

### Sync all findings

Sync every finding in the active project:

```
[acme-audit]> sync --integration=defectdojo
Sync complete: 142 exported
```

### Sync findings from a specific scan run

Sync only findings from a particular scan run by its ID:

```
[acme-audit]> sync --integration=defectdojo --run-id=3
Sync complete: 28 exported
```

### Override engagement type

Pass `--engagement-type` to override the configured engagement type
for a single sync:

```
[acme-audit]> sync --integration=defectdojo --engagement-type="Manual Assessment"
Sync complete: 142 exported
```

### CLI (for automation)

The CLI exposes the same export via `--command integration-sync`,
suitable for crontab or CI pipelines:

```bash
# Export all findings
python3 tally-cli.py --project myapp --command integration-sync

# Export a specific scan run
python3 tally-cli.py --project myapp --command integration-sync --run-id 5

# Override engagement type
python3 tally-cli.py --project myapp --command integration-sync --engagement-type "CI/CD"
```

Schedule it with cron to sync periodically:

```bash
# Every 6 hours
0 */6 * * * cd /opt/tally && .venv/bin/python3 tally-cli.py --project myapp --command integration-sync >> /var/log/tally-sync.log 2>&1
```

See [docs/cli.md](../cli.md) for the full CLI reference.

---

## How findings are mapped

Each Tally finding is converted to a DefectDojo Generic Finding with
the following field mapping:

| Tally field | DefectDojo field | Notes |
|---|---|---|
| `severity` | `severity` | Mapped to DefectDojo levels: Critical, High, Medium, Low, Info |
| `description` | `description` | Falls back to synthesized title if absent |
| `status` | `active`, `false_p`, `is_mitigated` | `active` maps to active, `false_positive` maps to false_p, `fixed` maps to is_mitigated |
| `confidence` | `verified`, `scanner_confidence` | `confirmed` sets verified to true |
| `fingerprint` | `unique_id_from_tool` | Used by DefectDojo for deduplication |
| `cwe` | `cwe` | First CWE from the list, parsed as integer |
| `vulnerability_id` | `cve`, `vuln_id_from_tool` | CVE IDs are set in both fields |
| `file` | `file_path` | Source file path |
| `domain` | `static_finding`, `dynamic_finding` | `code` sets static, `web` sets dynamic |
| `finding_type`, `domain`, `segment`, `tool` | `tags` | Assembled into a tag list |

### Per-tool enrichment

Tools with dedicated mappers add extra fields:

| Tool | Additional fields |
|---|---|
| `semgrep` | `line`, `sast_source_file_path`, `references` |
| `gitleaks` | `line`, `vuln_id_from_tool` |
| `zap`, `dalfox`, `xsstrike` | `param`, `payload`, `endpoints` |
| `garak` | `service`, `description` (probe + goal), probe/detector tags |
| `osv`, `npm-audit`, `pip-audit`, `composer-audit` | `component_name`, `component_version`, `fix_version`, `cvssv3_score`, `cvssv3`, `references`, `impact` |

Findings from tools without a dedicated mapper are exported using the
base mapping. No findings are dropped due to missing tool support.

---

## Deduplication and mitigation

Tally groups findings by repo and tool, then creates a separate
DefectDojo Product for each repo and a separate Test for each tool
within the Engagement. When you sync, each (repo, tool) combination
is reimported independently. Tools that ran but produced zero findings
still appear as Tests with an empty finding list, giving full
visibility into what was scanned.

Within each Test, DefectDojo matches findings by
`unique_id_from_tool` (the Tally fingerprint) and updates existing
records instead of creating duplicates.

**Mitigation behavior.** When a finding's fingerprint is absent from
a subsequent sync of the same tool against the same repo, DefectDojo
automatically marks it as mitigated. This means:

- Finding in scan 1, present in scan 2: stays active
- Finding in scan 1, absent in scan 2: marked mitigated
- Finding in scan 1, no scan 2 yet: stays in current state

Because each repo is its own Product, scanning repo B never affects
repo A's findings. Scanning with a new tool never affects existing
tools' findings.

---

## Endpoint export

After exporting findings, Tally sends discovered URL endpoints to
DefectDojo. These come from the `url_findings` table (populated by
katana, noir, user-provided URL lists, and xsstrike crawl results).

Each endpoint is deduplicated by protocol, host, port, and path
before being sent. Query parameters are not included.

### Filtering

Only endpoints belonging to the scanned repos are exported. An
endpoint "belongs to" a repo if its host and port match one of the
repo's configured `base_urls`. This excludes:

- Third-party sites and CDN URLs
- External API references found by crawlers
- Static assets (`.js`, `.css`, `.svg`, `.png`, fonts, etc.)

### How endpoints appear in DefectDojo

Each endpoint is created in the DefectDojo Product corresponding to
its repo. DefectDojo associates findings with endpoints by matching
the finding's endpoint URL against the endpoint's host, port, and
path. If a finding references a matching URL, the endpoint shows as
"Vulnerable" with a count of active findings.

Endpoints with no matching findings still appear in the Endpoints tab,
giving visibility into the full attack surface of each repo.

---

## Custom scan type

By default, Tally uses the `Generic Findings Import` scan type. This
means the **Found By** column in DefectDojo shows "Generic Findings
Import". To display a custom label like "Tally", register a custom
scan type in DefectDojo and configure Tally to use it.

### Step 1: Create the scan type in DefectDojo

1. Log in to DefectDojo as a superuser.
2. Go to the Django admin panel at `/admin/dojo/test_type/`.
3. Click **Add Test Type**.
4. Set **Name** to `Tally`.
5. Save.

### Step 2: Configure Tally to use it

Add `scan_type` to the `defectdojo` block in `config/global.json`:

```json
{
  "defectdojo": {
    "url": "https://defectdojo.internal.example.com",
    "api_token": "your-api-token-here",
    "scan_type": "Tally"
  }
}
```

The name must match the test type you created in DefectDojo exactly.
If the test type does not exist in DefectDojo, the sync will fail with
a 400 error.

---

## Automatic post-scan sync

Tally can automatically sync findings to DefectDojo after every
successful scan. Add `"defectdojo"` to the `post_scan_sync` array in
`config/global.json`:

```json
{
  "post_scan_sync": ["defectdojo"]
}
```

When enabled, Tally syncs the findings from the completed scan run
immediately after the scan finishes. The sync uses the same
configuration (connection, product type, engagement type) as a manual
`sync` command. Only findings from the scan run that triggered the
hook are exported, not the full project history.

The sync is best-effort: if the DefectDojo instance is unreachable or
misconfigured, the scan result is still reported as successful. Sync
failures are logged but never mask scan results.

To disable, remove `"defectdojo"` from the array or set
`post_scan_sync` to an empty list.

---

## Automatic post-triage sync

Tally can automatically re-sync findings to DefectDojo after triage
completes. Add `"defectdojo"` to the `post_triage_sync` array in
`config/global.json`:

```json
{
  "post_triage_sync": ["defectdojo"]
}
```

When enabled, Tally re-exports findings for the triaged scan run
immediately after triage finishes. The export uses the `reimport-scan`
endpoint, which deduplicates on fingerprint. DefectDojo updates
existing records with triage-enriched fields: confidence, severity,
finding type, remediation guidance, and false positive status.

The sync is best-effort: if the DefectDojo instance is unreachable or
misconfigured, the triage result is still reported as successful. Sync
failures are logged but never mask triage results.

To disable, remove `"defectdojo"` from the array or set
`post_triage_sync` to an empty list.

---

## Troubleshooting

**"DefectDojo connection not configured."** Add a `defectdojo` section
to `config/global.json` with at least `url` and `api_token`.

**"Authentication failed: invalid or expired API token."** Verify the
token in `config/global.json` matches a valid API v2 key in DefectDojo.
Tokens can be regenerated from the user profile page.

**"DefectDojo connection failed."** Check that the URL is correct and
the instance is reachable. If using a self-signed certificate, set
`verify_ssl` to `false` in `config/global.json`.

**Some findings show "failed to map."** The mapper was unable to convert
those findings to the DefectDojo format. Check the Tally log for
details. This typically indicates a finding with missing required fields.
