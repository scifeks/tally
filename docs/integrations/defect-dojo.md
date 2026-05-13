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

## Configuration

Configuration is split across two files. Connection settings live in
`config/global.json` (one DefectDojo instance for all projects).
Targeting settings live in each project's `project.json` (which
DefectDojo product and engagement to export into).

### Global: connection settings

Add a `defectdojo` block to `config/global.json`:

```json
{
  "defectdojo": {
    "url": "https://defectdojo.internal.example.com",
    "api_token": "your-api-token-here",
    "verify_ssl": true
  }
}
```

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | | Base URL of your DefectDojo instance. Must use `http://` or `https://`. |
| `api_token` | string | Yes | | API v2 token from your DefectDojo user profile. |
| `verify_ssl` | bool | No | `true` | Verify TLS certificates. Set to `false` for self-signed certificates. |

### Project: targeting settings

Add a `defectdojo` block to the project config at
`projects/<name>/project.json`:

```json
{
  "project_name": "acme-audit",
  "defectdojo": {
    "product_name": "ACME Web App",
    "engagement_name": "Q2 2025 Security Audit"
  }
}
```

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `product_name` | string | Yes | | DefectDojo product to export into. Created automatically if `auto_create_context` is `true`. |
| `engagement_name` | string | Yes | | DefectDojo engagement within the product. Created automatically if `auto_create_context` is `true`. |
| `product_type_name` | string | No | `"Tally"` | Product type assigned when auto-creating the product. |
| `auto_create_context` | bool | No | `true` | Create the product, engagement, and product type in DefectDojo if they do not exist. |

---

## Usage

### Test the connection

Verify that Tally can reach your DefectDojo instance and authenticate:

```
[acme-audit]> export defectdojo --test-connection
DefectDojo connection successful.
```

### Export all findings

Export every finding in the active project:

```
[acme-audit]> export defectdojo
Export complete: 142 exported
```

### Export findings from a specific scan run

Export only findings from a particular scan run by its ID:

```
[acme-audit]> export defectdojo --run-id=3
Export complete: 28 exported
```

### CLI (for automation)

The CLI exposes the same export via `--command integration-sync`,
suitable for crontab or CI pipelines:

```bash
# Export all findings
python3 tally-cli.py --project myapp --command integration-sync

# Export a specific scan run
python3 tally-cli.py --project myapp --command integration-sync --run-id 5
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

## Deduplication

Tally uses the DefectDojo reimport-scan endpoint. On repeated exports,
DefectDojo matches findings by `unique_id_from_tool` (the Tally
fingerprint) and updates existing records instead of creating
duplicates. Findings that no longer appear in the export are
automatically marked as mitigated by DefectDojo.

---

## Troubleshooting

**"DefectDojo connection not configured."** Add a `defectdojo` section
to `config/global.json` with at least `url` and `api_token`.

**"DefectDojo targeting not configured for project."** Add a
`defectdojo` section to the project's `project.json` with at least
`product_name` and `engagement_name`.

**"Authentication failed: invalid or expired API token."** Verify the
token in `config/global.json` matches a valid API v2 key in DefectDojo.
Tokens can be regenerated from the user profile page.

**"DefectDojo connection failed."** Check that the URL is correct and
the instance is reachable. If using a self-signed certificate, set
`verify_ssl` to `false` in `config/global.json`.

**Some findings show "failed to map."** The mapper was unable to convert
those findings to the DefectDojo format. Check the Tally log for
details. This typically indicates a finding with missing required fields.
