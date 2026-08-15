# MCP finding payload shape

The exact JSON shape every scanner subagent must return for each
finding. The orchestrator hands each finding to Tally's
`submit_finding` MCP tool, which validates the payload server-side.
Any deviation is rejected per finding.

Authoritative validator source:
`application/mcp/finding_payload.py`. Authoritative skill IDs, primary
CWEs, parent labels, OWASP names, and default severities:
`docs/roadmap/TAL-148/taxonomy.md` T3.

## Required top-level fields

| Field | Type | Values | Notes |
|---|---|---|---|
| `file` | string | any repo-relative path | Alias: `file_path`. One or the other must be present. |
| `line_number` | int | positive | Alias: `line_start`. Points at the sink line. |
| `description` | string | non-empty | Prose the report card renders. |
| `severity` | string | `critical`, `high`, `medium`, `low`, `informational` | Take the default from taxonomy T3 for the skill; bump up when the sink reaches production data or bump down when the sink is dev-only. |
| `confidence` | string | `confirmed`, `probable`, `potential`, `false_positive` | `confirmed` when a taint source is traced end to end; `probable` when the sink pattern matches but the source is inferred; `potential` when the sink is suspicious but the source is unknown. |
| `cwe` | list of strings | `["CWE-N", ...]` | Non-empty. Primary CWE first. Take the primary from taxonomy T3. |
| `finding_type` | list of strings | non-empty | `["vulnerability"]` for security defects; `["misconfiguration"]` for framework-defaults; `["secret"]` for hardcoded credentials. |
| `rule_id` | string | dot-notation skill ID | Exactly the skill ID from taxonomy T3, e.g. `injection.sql`, `xss.stored`, `access_control.idor_bola`. Per D22, `rule_id` carries the skill identity; the server reads it back through the report `_get_title` and OWASP-name fallbacks. |
| `meta` | dict | see below | Required keys: `title`, `owasp_name`, `remediation`. |

## Required meta fields

| Field | Type | Notes |
|---|---|---|
| `meta.title` | string | Short human title the report card shows, e.g. `"SQL injection via string-formatted query"`. |
| `meta.owasp_name` | string | OWASP Top 10:2025 category NAME, not the numeric identifier. Take from taxonomy T6. Examples: `Injection`, `Broken Access Control`, `Cryptographic Failures`. |
| `meta.remediation` | string | Per D19, the scanner writes this inline based on the actual library or framework observed in the scanned code. See `skill-template.md` for guidance. |

## Optional top-level fields

| Field | Type | Notes |
|---|---|---|
| `segment` | string | Default `sast`. Enum: `sast`, `sca`, `secrets`, `web`, `llm`. Scanner skills are overwhelmingly `sast`; leave unset unless the skill emits web (URL-bearing) or SCA (package-version-bearing) findings. |
| `line_end` | int | End line if the sink spans multiple lines. |
| `reasoning` | string | Why this is a real defect. Falls into `meta`. |
| `remediation` | string | Falls into `meta` at the top level. Prefer `meta.remediation` (the required key) so payload shape stays consistent. |
| `attack_vector` | string | How an attacker would trigger the sink. Falls into `meta`. |
| `code_snippet` | string | 2-6 lines of source containing the sink. Falls into `meta`. |

## Optional meta fields

Unknown `meta.*` keys pass validation and land on the finding row.
Useful additions:

- `meta.line_start` and `meta.line_end` for multi-line sinks the
  report should render as a range.
- `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.
- `meta.method`, `meta.url` for web-segment findings.
- `meta.package_name`, `meta.package_version`, `meta.ecosystem`
  for sca-segment findings.

## Server-set fields

The scanner does NOT provide these; the server sets them at insert
time:

- `tool = "claudecode"` (D2; shared with Part 1 internal LLM scan).
- `domain = "llm"`.
- `triaged_by = "claudecode"`, `triaged_at = <now>` (D9; MCP-ingested
  findings self-triage at discovery time and skip the batch triage
  flow).
- `status = "active"`.
- `should_report = True` (D18; findings render in the report
  immediately without an analyst gate).
- `duplicate_of = NULL` on insert; set later by
  `resolve_duplicates` if the LLM picks a survivor.

## Example: injection.sql finding

```json
{
  "file": "app/models/user.py",
  "line_number": 47,
  "description": "The username parameter from the login form is interpolated directly into a SQL query using an f-string. An attacker can inject SQL by submitting a crafted username such as `admin' OR '1'='1' --`.",
  "severity": "critical",
  "confidence": "confirmed",
  "cwe": ["CWE-89"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.sql",
  "meta": {
    "title": "SQL injection via string-formatted query",
    "owasp_name": "Injection",
    "remediation": "Replace the f-string with a parameterized query. The sqlite3 module uses `?` placeholders; call `cursor.execute('SELECT * FROM users WHERE username = ?', (username,))`.",
    "code_snippet": "def login(username, password):\n    cursor = db.cursor()\n    query = f\"SELECT * FROM users WHERE username = '{username}'\"\n    cursor.execute(query)",
    "taint_source": "request.form['username']",
    "attack_vector": "Attacker submits a login form with a crafted username; the injected SQL runs with the database user's full privileges."
  }
}
```

## Validator behavior

The validator lives at `application/mcp/finding_payload.py`. It
rejects unknown top-level keys with an error naming the first
unknown field found. Unknown `meta.*` keys pass through and land on
the finding row. On per-finding failure, `submit_finding` returns
`{"finding_id": null, "status": "rejected", "error": "<message>"}`;
the orchestrator should log the error and continue submitting the
rest of the batch.

## What "developer-ready" means

Per Part 2's fidelity criterion, every MCP-ingested finding must
render as if a triaged Tally finding. The report reads:

- `meta.title` first, then `rule_id` as fallback (per D22, `rule_id`
  is the dot-notation skill name, so the fallback still reads).
- `meta.remediation` (or `meta.triage.remediation` if present, but
  MCP-ingested findings do not populate the triage sub-key).
- `severity`, `confidence`, `status`, `description` as columns.
- `file:line_number` for SAST segments.
- `meta.owasp_name` first, then first CWE, then `rule_id` for the
  OWASP category label.

A finding that omits `meta.title` or `meta.remediation` still
renders, but shows fallback text that reads as machine-generated.
Populate both for every finding.
