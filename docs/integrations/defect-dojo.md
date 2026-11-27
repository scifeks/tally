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

| Tally concept | DefectDojo concept | Notes |
|---|---|---|
| Project `company_name` | **Organization** (Product Type) | Groups every repo of the project. Falls back to the project name when `company_name` is empty. Projects with the same `company_name` share one Organization. |
| Repository | **Product** (Asset) | Named `<project> / <repo>`. One per active repository. |
| Resolved `engagement_name` | **Engagement** | One per Product. Type is always Interactive. If Tally cannot change the type (for example the API user lacks permission), the Engagement stays CI/CD, the sync still succeeds, and a warning is logged. Default name: `"Tally Engagement"`. |
| Tool | **Test** | One per tool, titled with the tool name. |
| Finding | **Finding** | One per Tally finding. |

DefectDojo 3.x labels a Product Type as an Organization and a Product as an Asset. The API names are unchanged.

---

## Configuration

Configuration is split across two levels. Connection settings and
defaults live in `config/global.json` (shared across all projects).
An optional project-level override in `project.json` can set a
per-project Engagement name.

### Global settings

Add a `defectdojo` block to `config/global.json`:

```json
{
  "defectdojo": {
    "url": "https://defectdojo.internal.example.com",
    "api_token": "your-api-token-here",
    "verify_ssl": true,
    "engagement_name": "Tally Engagement"
  }
}
```

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | | Base URL of your DefectDojo instance. Must use `http://` or `https://`. |
| `api_token` | string | Yes | | API v2 token from your DefectDojo user profile. |
| `verify_ssl` | bool | No | `true` | Verify TLS certificates. Set to `false` for self-signed certificates. |
| `engagement_name` | string | No | `"Tally Engagement"` | Name of the Engagement created in each Product. Can be overridden per project and per command. |
| `auto_create_context` | bool | No | `true` | Create the Organization, Product, and Engagement in DefectDojo if they do not exist. |
| `scan_type` | string | No | `"Generic Findings Import"` | DefectDojo scan type (test type) used for the import. Controls the "Found By" label. See [Custom scan type](#custom-scan-type). |

### Project-level override (optional)

You can override `engagement_name` per project by adding a `defectdojo`
block to `projects/<name>/project.json`:

```json
{
  "project_name": "acme-audit",
  "defectdojo": {
    "engagement_name": "Q4 Audit"
  }
}
```

This is optional. If omitted, the global `engagement_name` is used.

### Engagement name resolution

The Engagement name follows a three-tier cascade:

1. **Command flag** `--engagement-name`
2. **Project config** `defectdojo.engagement_name`
3. **Global config** `defectdojo.engagement_name` (default)

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

### Limit a sync to one scan run

`--run-id` limits the sync to the repositories and tools that scan run
touched. Tally still sends their current state, not that run's findings:

```
[acme-audit]> sync --integration=defectdojo --run-id=3
Sync complete: 28 exported
```

The automatic syncs after a scan or triage always sync the whole project.

### Override the Engagement name

Pass `--engagement-name` to override the configured Engagement name
for a single sync:

```
[acme-audit]> sync --integration=defectdojo --engagement-name="Manual Assessment"
Sync complete: 142 exported
```

### CLI (for automation)

The CLI exposes the same export via `--command integration-sync`,
suitable for crontab or CI pipelines:

```bash
# Export all findings
python3 tally-cli.py --project myapp --command integration-sync

# Sync only the repositories and tools that scan run 5 touched
python3 tally-cli.py --project myapp --command integration-sync --run-id 5

# Override the Engagement name
python3 tally-cli.py --project myapp --command integration-sync --engagement-name "Q4 Audit"
```

Schedule it with cron to sync periodically:

```bash
# Every 6 hours
0 */6 * * * cd /opt/tally && .venv/bin/python3 tally-cli.py --project myapp --command integration-sync >> /var/log/tally-sync.log 2>&1
```

See [docs/cli.md](../cli.md) for the full CLI reference.

---

## What a sync sends

Every sync sends the current state of the project. For each active repository, Tally sends one batch per tool, and each batch updates that tool's Test in the repository's Product.

Tally syncs only active repositories. A finding with no repository is not sent, and a removed repository gets no batches.

### Scanner tools

For each service in a repository, Tally sends the findings from the most recent scan in which the tool finished on that service. When that scan found nothing, Tally still sends the empty result, and DefectDojo closes the findings that Test still holds open.

A tool that was skipped, failed, or was not part of a scan has no effect. Tally keeps using the last scan in which the tool finished.

### Accumulating tools

Findings added by hand, findings from Claude Code and OpenCode scans, and Burp findings are never closed because a later scan did not report them. Tally sends every finding from these tools and collapses repeats to the newest copy. A finding from these tools closes in DefectDojo only when you change its status in Tally.

### Statuses

| Tally status | DefectDojo state |
|---|---|
| `active` | Active |
| `false_positive` | Inactive, false positive |
| `fixed` | Inactive, mitigated |
| `wont_fix` | Inactive, risk accepted |

### Known limitation

A scan limited to the files changed since a commit is treated as a full scan. Syncing after one closes that tool's findings in files the scan did not read. Run a full scan before syncing to restore them.

---

## How findings are mapped

Each Tally finding is converted to a DefectDojo Generic Finding with
the following field mapping:

| Tally field | DefectDojo field | Notes |
|---|---|---|
| `severity` | `severity` | Mapped to DefectDojo levels: Critical, High, Medium, Low, Info |
| `description` | `description` | Falls back to synthesized title if absent |
| `status` | `active`, `false_p`, `is_mitigated`, `risk_accepted` | `active` maps to active, `false_positive` maps to false_p, `fixed` maps to is_mitigated, `wont_fix` maps to risk accepted. See [Statuses](#statuses) |
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
is reimported independently. A tool with no stored finding on a repo
never gets a Test. Tally sends an empty batch only for a scanner tool
that has findings on that repo and finished a newer scan with none,
which closes them.

Within each Test, DefectDojo matches findings by
`unique_id_from_tool` (the Tally fingerprint) and updates existing
records instead of creating duplicates.

**Mitigation behavior.** When a finding's fingerprint is absent from
a batch sent for a scanner tool, DefectDojo automatically marks it as
mitigated. This means:

- Finding in scan 1, present in scan 2: stays active
- Finding in scan 1, absent in a clean scan 2: marked mitigated
- Finding in scan 1, tool skipped or failed in scan 2: stays in current state

Because each repo is its own Product, scanning repo B never affects
repo A's findings. Scanning with a new tool never affects existing
tools' findings. See [What a sync sends](#what-a-sync-sends) for which
findings each tool contributes.

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

When enabled, Tally syncs the project immediately after the scan
finishes. The sync uses the same configuration (connection, Organization,
Engagement name) as a manual `sync` command. Automatic syncs always
sync the whole project, not only the scan run that triggered them.

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

When enabled, Tally syncs the whole project immediately after triage
finishes, not only the triaged scan run. The export uses the
`reimport-scan` endpoint, which deduplicates on fingerprint. DefectDojo updates
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

**Some findings show "failed to map."** The mapper could not convert
those findings to the DefectDojo format. Check the Tally log for
details. This typically indicates a finding with missing required fields.

---

## Moving from the fixed Organization

Earlier versions placed every Product under one Organization named `Tally Scan`. DefectDojo rejects a sync when a Product already exists under a different Organization.

1. In DefectDojo, delete the `Tally Scan` Organization. This deletes its Products and findings.
2. In `config/global.json`, remove `product_type` and rename `engagement_type` to `engagement_name`. Tally fails to load the config while either old name is present, so every Tally command that loads it fails.
3. In each project's `config/project.json`, rename `engagement_type` to `engagement_name` under `defectdojo`. The project config fails to load while the old name is present.
4. Run a sync. Tally creates the new Organizations.
