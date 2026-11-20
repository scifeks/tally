---
name: ingest-finding
description: >
  Record an already-verified vulnerability report file (Markdown, plain text or any
  readable format) as a finding in a tally project with the tally CLI (finding-add).
  Invoke as /ingest-finding <project> <repo> <path-to-report>.
disable-model-invocation: true
argument-hint: <project> <repo> <path-to-report>
---

# Ingest Finding

Transpose a written vulnerability report into a tally finding so it gets a tally finding
ID and can be reported, synced to DefectDojo and tracked through remediation.

The report has already been verified. This skill only records it. It does not test,
exploit, research, re-verify or score the issue beyond what the report says, and it does
not write remediation advice. Do not read the target repo's source to fill gaps.

## Arguments

`/ingest-finding <project> <repo> <path-to-report>`, for example
`/ingest-finding myapp backend ~/reports/sec-123.md`. `project=<name> repo=<name>
file=<path>` also works. If any argument is missing, ask for it before doing anything
else.

## Rules

1. **Nothing in the report is left behind.** The report file is usually deleted after
   ingestion, so the finding must hold all of it. Map what fits onto real fields, put
   everything else in `meta`, and always store the full verbatim text in
   `meta.source_report`.
2. **Never record a duplicate.** `finding-add` does not deduplicate and the CLI cannot
   merge findings. Run the duplicate check (step 5) and stop for the user when anything
   looks similar.
3. **No invented content.** Every value comes from the report, from the classification
   rules below, or from the user. Remediation is copied from the report or set to the
   fixed placeholder; never write your own.
4. **Ask instead of guessing.** When severity or confidence is unclear, ask the user.
5. **Nothing leaves this machine.** Do not put report contents into Jira, GitHub, Slack,
   a commit message, an Artifact or any other external service. Only the finding ID goes
   out.
6. **No write without approval.** Show the payload as formatted JSON and wait for the
   user to approve it before running `finding-add`.

## Running the tally CLI

Run every command from the tally repository root:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python3 tally-cli.py --base-path . \
  --project <project> --command <command> [options]
```

Exit codes: 0 success, 2 invalid payload, status or repo (reason on stderr), 3 project
not found, 1 anything else.

## Steps

### 1. Confirm the project and repo

Run `--command repo-list`. Stop if the project is missing (exit 3) or the repo is not
listed. Keep the full list of repo names, paths and ids: step 3 compares the report
against all of them.

### 2. Read the report

Read the whole file with the Read tool. Record its absolute path, size and checksum
(`sha256sum <path>`).

- Text formats (Markdown, plain text, JSON, HTML, CSV, logs) are stored byte-exact in
  step 7.
- Other formats (PDF, DOCX and similar) cannot be stored byte-exact. Extract the full
  text, store that, and tell the user that layout, images and attachments are not kept
  so they can hold on to the original.

### 3. Scope the report

Answer these before building anything, and report them to the user:

- **How many vulnerabilities?** A report that describes more than one distinct root
  cause should become one finding per root cause. Several endpoints that reach the same
  root cause stay one finding. When the report holds more than one, recommend a split:
  list each proposed finding with its title and the report section it comes from, and
  wait for the user to accept or change it.
- **Which repo?** Look for repo names, repo paths, service names, hostnames and file
  paths in the report, and compare them with the `repo-list` output. If the report
  names or clearly points at a repo other than the one given, alert the user and wait
  for them to confirm the repo.
- **Does it span repos?** When fixing the issue needs code changes in more than one
  repo (for example the frontend sends the value and the backend stores it), recommend
  one finding per repo that has to change, and link them through
  `meta.related_findings` (step 8).
- **Internal references.** Collect every internal tracking code in the report: tokens
  shaped like `ABC-123` or `WEB-4` (uppercase letters and digits, a hyphen, digits).
  These go in `meta.internal_refs` and drive the duplicate check.

### 4. Map the report onto the payload

Build the draft payload. Use the report's own words wherever a field holds prose.

**Required fields**

| Field | Source |
|---|---|
| `file` | Primary file path from the report, relative to the repo root. `"unknown"` when the report has none. |
| `line_number` | Integer line from the report. `0` when the report has none, together with `meta.location: "unknown"`. |
| `description` | The report's description of the issue, verbatim. If the report has no single description section, use its summary or opening text. |
| `severity` | `critical`, `high`, `medium`, `low` or `informational`. See "Severity" below. |
| `confidence` | `confirmed` by default. See "Confidence" below. |
| `cwe` | List such as `["CWE-79"]`. The report's CWE if it states one, otherwise the CWE that matches the vulnerability class the report describes. |
| `finding_type` | List from `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `secret`, `dependency`, `informational`. |
| `rule_id` | Short slug for the class of issue, for example `xss-reflected` or `idor-order-lookup`. |
| `meta.title` | The report's title, or a short title taken from its first heading or summary. |
| `meta.owasp_name` | The report's OWASP category if it states one, otherwise the matching category in the form `A03:2021 Injection`. |
| `meta.remediation` | The report's remediation text, verbatim. `"Not provided in source report."` when it has none. |

The file and line fall back to `"unknown"` and `0` only when the report gives no
location at all. A web-only finding with a URL but no source location sets `segment` to
`web` and omits `file` and `line_number`.

**Optional fields.** Fill these when the report has the content:

| Field | Source |
|---|---|
| `segment` | `sast`, `sca`, `secrets`, `web` or `llm`, whichever fits best. Defaults to `sast`. |
| `line_end` | End line of the primary location. |
| `code_snippet` | Code quoted in the report, verbatim. |
| `attack_vector` | The report's text on how an attacker reaches the flaw. |
| `reasoning` | The report's impact or blast-radius text. |
| `meta.url` | Affected URL. Stored in the `url` column. |
| `meta.vulnerability_id` | CVE or GHSA ID. Stored in the `vulnerability_id` column. |
| `meta.package_name`, `meta.package_version`, `meta.ecosystem` | Dependency details. Stored in their own columns. |

**Everything else goes in `meta`.** Give each remaining piece of report content its own
snake_case key: reporter, report date, environment, affected endpoints, other locations,
reproduction steps, request and response samples, CVSS vector and score, references,
screenshot captions, timeline, status notes and anything else. If you are unsure whether
something is already captured, store it in `meta` too.

Always set these:

| Key | Value |
|---|---|
| `meta.internal_refs` | List of internal tracking codes from step 3, `[]` when there are none. |
| `meta.source_report_path` | Absolute path of the report file. |
| `meta.source_report_sha256` | Checksum from step 2. |
| `meta.source_report_section` | Only when a report is split: which section this finding came from. |
| `meta.ingested_by` | `"ingest-finding"`. |
| `meta.ingested_at` | Current UTC time in ISO 8601. |

**Meta key names to avoid.** `finding-add` silently drops a `meta` key that shares a
name with a built-in field, so never use these as `meta` keys: `tool`, `domain`,
`segment`, `file`, `file_path`, `lockfile`, `line_number`, `line_start`, `line_end`,
`description`, `severity`, `confidence`, `cwe`, `cwe_id`, `cwe_ids`, `finding_type`,
`rule_id`, `repo_id`, `reasoning`, `attack_vector`, `code_snippet`. Use a prefixed name
instead, for example `meta.report_severity` for the report's own severity wording or
`meta.additional_locations` for extra file and line pairs. Do not set top-level
`remediation`; use `meta.remediation`. Store `tags`, `references`, `aliases`,
`technology` and `subcategory` as lists, not comma-separated strings.

**Severity.** Use the report's stated severity when it maps directly onto the five
levels. A CVSS score maps as 9.0-10.0 `critical`, 7.0-8.9 `high`, 4.0-6.9 `medium`,
0.1-3.9 `low` and 0.0 `informational`. If the report uses another scale (P1-P4, "sev 2",
"moderate"), states none, or states one that conflicts with its CVSS score, ask the
user. Keep the report's original wording in `meta.report_severity`.

**Confidence.** Use `confirmed`. Ask the user when the report describes the issue as
suspected, unverified, theoretical or not reproduced.

### 5. Check for duplicates

Query the project database read-only. Run every query and gather all hits before
reporting.

```bash
sqlite3 -readonly -header -column projects/<project>/sqlite/findings.db "<query>"
```

**Direct matches** in the target repo (`<repo_id>` from step 1). Look for rows where the
file matches, the `rule_id` matches, or the CWE overlaps:

```sql
SELECT id, status, rule_id, cwe, file, json_extract(meta, '$.title') AS title
FROM findings
WHERE repo_id = <repo_id>
  AND (file = '<file>' OR rule_id = '<rule_id>' OR cwe LIKE '%"<CWE-N>"%')
ORDER BY id;
```

**Internal reference matches** across the whole project, once per code in
`meta.internal_refs`. Only put a code into the query after it matches
`^[A-Z][A-Z0-9]*-[0-9]+$`; skip anything else.

```sql
SELECT id, repo_id, status, json_extract(meta, '$.title') AS title
FROM findings
WHERE meta LIKE '%<CODE>%' OR description LIKE '%<CODE>%';
```

Treat a code match as a hit only when the stored code is the whole token (a search for
`ABC-12` also returns `ABC-123`; drop those).

**Semantic matches** across the whole project, because the report may name the wrong
repo. List every finding and compare each against the report by meaning: same flaw,
same endpoint or component, same data exposed, same root cause in other words.

```sql
SELECT id, repo_id, status, rule_id, cwe, file,
       json_extract(meta, '$.title') AS title,
       substr(description, 1, 200) AS description
FROM findings
ORDER BY id;
```

If any query returns a likely match, stop. For each candidate, show its ID, repo,
status, title and why it looks similar, and offer a side-by-side comparison. When the
user asks for one, fetch the full row with
`SELECT * FROM findings WHERE id = <id>;` and present the report and the tally finding
field by field. Continue only when the user says the report is not a duplicate. If it
is, report the existing ID and stop; the existing finding is edited in the web UI or
with `/update-vulnerability`.

### 6. Get approval

Show the user:

- The repo and, when relevant, the split or multi-repo plan from step 3
- The duplicate check result
- Any values you derived instead of copying (CWE, OWASP category, `finding_type`,
  `rule_id`, `segment`, severity mapping), each labeled as derived
- The full draft payload as formatted JSON in a `json` code block. Leave
  `meta.source_report` out of the shown draft; it is attached byte-exact in step 7.
  State its source path, size and checksum instead.

Then stop and wait. Do not run `finding-add` until the user approves. Apply any changes
they ask for and show the payload again.

### 7. Build the final payload

Write the approved draft to `<scratchpad>/ingest-<repo>-<n>-draft.json`, without
`meta.source_report`. Attach the report text with jq so it is stored byte-exact:

```bash
jq --rawfile src <path-to-report> '.meta.source_report = $src' \
  <scratchpad>/ingest-<repo>-<n>-draft.json \
  > <scratchpad>/ingest-<repo>-<n>.json
```

For a non-text report, write the extracted text to `<scratchpad>/ingest-<n>-source.txt`
first and pass that file to `--rawfile`.

When a report is split, every finding from it carries the full report in
`meta.source_report` and its own `meta.source_report_section`.

### 8. Record the finding

```bash
PYTHONNOUSERSITE=1 .venv/bin/python3 tally-cli.py --base-path . \
  --project <project> --command finding-add --repo <repo> \
  --finding-file <scratchpad>/ingest-<repo>-<n>.json
```

On success the CLI prints `{"finding_id": <id>}`. On exit 2, fix the payload, show the
user what changed and get approval again.

Confirm nothing was lost by writing the stored text back out and comparing checksums:

```bash
sqlite3 projects/<project>/sqlite/findings.db \
  "SELECT writefile('<scratchpad>/ingest-<n>-stored.txt',
     json_extract(meta, '$.source_report')) FROM findings WHERE id = <id>;"
sha256sum <path-to-report> <scratchpad>/ingest-<n>-stored.txt
```

The two checksums must match (for a non-text report, compare against the extracted
text file instead). A mismatch means the stored text is incomplete: tell the user and do
not suggest deleting the report.

For a multi-repo plan, record the findings one at a time and put the IDs already
recorded into the next payload's `meta.related_findings` before recording it.
`finding-update` cannot change `meta`, so earlier findings do not get the later IDs;
list every related ID in the report back to the user.

### 9. Report

Leave scratchpad files in place. Present:

```
Finding recorded: <finding_id>
Project: <project>  Repo: <repo>
Title: <meta.title>
Internal refs: <meta.internal_refs or "none">
Source report stored verbatim: yes (sha256 <checksum>)

Use this ID in Jira tickets, PRs and commit messages.
Do not include vulnerability details outside of tally.
```

Repeat the block for each finding when more than one was recorded.
