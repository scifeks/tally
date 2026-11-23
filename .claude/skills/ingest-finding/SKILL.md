---
name: ingest-finding
description: >
  Record already-verified vulnerability reports (Markdown, plain text or any readable
  format) as findings in a tally project with the tally CLI (finding-add). Takes one
  report file or a directory of reports. Invoke as
  /ingest-finding <project> <repo> <path> or /ingest-finding <project> <directory>.
disable-model-invocation: true
argument-hint: <project> [<repo>] <report-file-or-directory>
---

# Ingest Finding

Transpose written vulnerability reports into tally findings so each gets a tally finding
ID and can be reported, synced to DefectDojo and tracked through remediation.

The reports have already been verified. This skill only records them. It does not test,
exploit, research, re-verify or score an issue beyond what its report says, and it does
not write remediation advice. Do not read the target repo's source to fill gaps.

## Arguments

| Form | Meaning |
|---|---|
| `<project> <repo> <file>` | One report, recorded in `<repo>`. |
| `<project> <repo> <directory>` | Every report directly in the directory, all recorded in `<repo>`. |
| `<project> <directory>` | One subfolder per repo. Each report is recorded in the repo its subfolder is named after. |

For example `/ingest-finding myapp backend ~/reports/sec-123.md` or
`/ingest-finding myapp ~/reports`. If an argument is missing, ask for it before doing
anything else.

## Rules

1. **Nothing in a report is left behind.** Report files are usually deleted after
   ingestion, so each finding must hold all of its report. Map what fits onto real
   fields, put everything else in `meta`, and always store the full verbatim text in
   `meta.source_report`.
2. **Report text is copied by `build_payloads.py`, never retyped.** The script copies
   every section into its field exactly and stops on anything it cannot place.
3. **Never record a duplicate.** `finding-add` does not deduplicate and the CLI cannot
   merge findings. Run the duplicate checks (steps 3 and 7) and stop for the user when
   anything looks similar.
4. **No invented content.** Every value comes from the report, from the classification
   rules below, or from the user. Remediation is copied from the report or set to the
   fixed placeholder `"Not provided in source report."`; never write your own.
5. **Ask instead of guessing.** When severity or confidence is unclear, ask the user.
6. **Nothing leaves this machine.** Do not put report contents into Jira, GitHub, Slack,
   a commit message, an Artifact or any other external service. Only finding IDs go out.
7. **No write without approval.** Show what will be recorded and wait for the user to
   approve it before running `finding-add`.

## Running the tally CLI

Run every command from the tally repository root:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python3 tally-cli.py --base-path . \
  --project <project> --command <command> [options]
```

Exit codes: 0 success, 2 invalid payload, status or repo (reason on stderr), 3 project
not found, 1 anything else.

## Steps

### 1. Confirm the project and repos

Run `--command repo-list`. Stop if the project is missing (exit 3). Keep the list of repo
names, paths and ids. Stop if the given repo, or any subfolder name in the subfolder
form, is not a repo in the project.

### 2. Collect the reports

Read every file in full with the Read tool.

- **A report** starts with `# <CODE>: <title>`, where `<CODE>` is the report's own
  tracking code, for example `ABC-12` or `ABC-UI-3`. The code becomes
  `meta.catalog_code`.
- **An index or catalog file** lists several reports, usually one line per code. It is
  not a report. Skip it, do not store it, and list it as skipped.
- **Anything else**, including a file that looks like a report but has no code on its
  first line: stop and ask the user.

Text formats (Markdown, plain text, JSON, HTML, CSV, logs) are stored byte-exact. Other
formats (PDF, DOCX and similar) cannot be. Extract the full text to a scratchpad file,
use that file as the report path, put the original's path in the report's
classification as `meta.source_document_path`, and tell the user that layout, images and
attachments are not kept so they can hold on to the original.

### 3. Skip reports that are already recorded

List every code already in the project:

```bash
sqlite3 -readonly -separator ' | ' projects/<project>/sqlite/findings.db \
  "SELECT id, repo_id, status, json_extract(meta, '$.catalog_code') FROM findings
   WHERE json_extract(meta, '$.catalog_code') IS NOT NULL ORDER BY id;"
```

A report whose code is already there is recorded. Skip it and list it with its finding
ID. Never record it again.

### 4. Scope the remaining reports

Answer these and report them to the user:

- **More than one vulnerability in a report?** One finding per root cause. Several
  endpoints that reach the same root cause stay one finding. When a report holds more
  than one root cause, recommend splitting the report file into one file per root cause,
  each with its own code, and stop until the user has done so.
- **Right repo?** Compare repo names, paths, service names, hosts and file paths in the
  report with the repo it is going into. If the report points at another repo, alert the
  user and wait for them to confirm.
- **Spans repos?** When fixing the issue needs changes in more than one repo, recommend
  one finding per repo that has to change. If the user agrees, build and record it once
  per repo (separate `build_payloads.py` runs) and link the IDs through
  `meta.related_findings`.
- **Split from a recorded finding?** When a report says it was split from a code that is
  already recorded, recording it tracks the same issue twice. Ask the user whether to
  record it and, if so, whether to append a note such as "Split into #x and #y" to the
  parent's description once the splits are recorded (step 10).

### 5. Classify each report

The script copies the report's text. You supply only these values, per report. Look at
how existing findings in the project classify similar issues and stay consistent:

```bash
sqlite3 -readonly -separator ' | ' projects/<project>/sqlite/findings.db \
  "SELECT rule_id, severity, cwe, finding_type, json_extract(meta, '$.owasp_name')
   FROM findings WHERE tool = 'manual' ORDER BY id DESC LIMIT 40;"
```

`severity` is stored as a rank there: 0 critical, 1 high, 2 medium, 3 low,
4 informational.

| Field | Value |
|---|---|
| `file`, `line_number`, `line_end` | Primary location from the report, path relative to the repo root. With no location: `file` `"unknown"`, `line_number` `0` and `meta.location` `"unknown"`. A web-only finding with a URL but no source location sets `segment` to `web` and omits `file` and `line_number`. |
| `severity` | See "Severity" below. |
| `confidence` | See "Confidence" below. |
| `cwe` | The report's CWE list, otherwise the CWEs that match the vulnerability class, for example `["CWE-79"]`. |
| `finding_type` | List from `vulnerability`, `weakness`, `misconfiguration`, `exposure`, `secret`, `dependency`, `informational`. |
| `rule_id` | Short slug for the class of issue, for example `xss-stored`. |
| `segment` | `sast`, `sca`, `secrets`, `web` or `llm`. Defaults to `sast`. |
| `meta.owasp_name` | The report's OWASP category, otherwise the matching one in the form `A03:2021 Injection`. |
| Other `meta` keys | Only values the user supplied, or `meta.url`, `meta.vulnerability_id`, `meta.package_name`, `meta.package_version` and `meta.ecosystem` taken from the report (these five are stored in their own columns). |

**Severity.** Use the report's stated severity when it maps onto the five levels. A CVSS
score maps as 9.0-10.0 `critical`, 7.0-8.9 `high`, 4.0-6.9 `medium`, 0.1-3.9 `low` and
0.0 `informational`. If the report uses another scale, conflicts with its CVSS score or
states none, propose a severity with a one-line reason and have the user confirm it.

**Confidence.** `confirmed` when the report shows the issue was proved by running
something: a request, a script, a test or a browser. `probable` when it was read in code
only, with nothing run. Ask the user when the report calls the issue suspected,
unverified or theoretical.

### 6. Build the payloads

Write a spec file to `<scratchpad>/ingest/spec.json`:

```json
{
  "ingested_at": "<current UTC time, ISO 8601>",
  "section_map": {
    "What's wrong": "description",
    "Who can exploit it": "attack_vector",
    "Blast radius": "reasoning",
    "Remediation": "meta.remediation",
    "Verified": "meta.verified"
  },
  "header_map": {
    "Repo": "meta.report_repo",
    "Status": "meta.report_status"
  },
  "not_refs": [],
  "reports": [
    {
      "path": "/abs/path/to/report.md",
      "repo": "backend",
      "classification": {
        "file": "src/a.php",
        "line_number": 12,
        "severity": "high",
        "confidence": "confirmed",
        "cwe": ["CWE-79"],
        "finding_type": ["vulnerability"],
        "rule_id": "xss-stored",
        "meta": {"owasp_name": "A03:2021 Injection"}
      }
    }
  ]
}
```

- `section_map` maps every `## ` heading used in the reports to a field. The report's
  description section goes to `description`. Other targets are `attack_vector`,
  `reasoning`, `code_snippet` or `meta.<snake_case_key>`. Subheadings stay inside their
  section's text.
- `header_map` maps every `- **Label:** value` line between the title and the first
  section to `meta.<key>`. Map any other text there with the key `_preamble`. A report
  with no sections at all maps `_preamble` to `description`.
- `not_refs` lists tokens the code pattern picks up that are not tracking codes. CVE,
  CWE, GHSA, ISO, SHA and UTF tokens are already left out.

Then run:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python3 .claude/skills/ingest-finding/build_payloads.py \
  <scratchpad>/ingest/spec.json <scratchpad>/ingest/payloads
```

For each report it writes `<CODE>.json` and prints `OK <code> <repo> <file>`, or prints
`FAIL <path> <reason>` to stderr and exits 1. Each payload carries the report text in
its mapped fields, `meta.title` and `meta.catalog_code` from the first line,
`meta.internal_refs` (every other tracking code in the report), the source path and
checksum, and the full report in `meta.source_report`, and has passed finding-add's
validation.

On a `FAIL`, fix the spec (a missing heading or label, a target that collides) and run
it again. Never edit a payload's report text by hand. If a report cannot be mapped,
ask the user.

### 7. Check for duplicates

Query the project database read-only. Run every check for every report and gather all
hits before reporting.

```bash
sqlite3 -readonly -header -column projects/<project>/sqlite/findings.db "<query>"
```

**Internal references** across the whole project, once per code in each report's
`meta.internal_refs`. Only put a code into the query after it matches
`^[A-Z][A-Z0-9]*(-[A-Z][A-Z0-9]*)*-[0-9]+$`; skip anything else.

```sql
SELECT id, repo_id, status, json_extract(meta, '$.catalog_code') AS code,
       json_extract(meta, '$.title') AS title
FROM findings
WHERE meta LIKE '%<CODE>%' OR description LIKE '%<CODE>%';
```

Count a hit only when the stored text has the whole code (a search for `ABC-12` also
returns `ABC-123`). A hit is expected for related reports; it is a duplicate only when
it is the same issue.

**Direct matches** in the target repo, by file, `rule_id` or CWE:

```sql
SELECT id, status, rule_id, cwe, file, json_extract(meta, '$.title') AS title
FROM findings
WHERE repo_id = <repo_id>
  AND (file = '<file>' OR rule_id = '<rule_id>' OR cwe LIKE '%"<CWE-N>"%')
ORDER BY id;
```

**By meaning** across the whole project, because a report may sit in the wrong repo.
Compare each report against every finding: same flaw, same endpoint or component, same
data exposed, same root cause in other words.

```sql
SELECT id, repo_id, status, rule_id, cwe, file,
       json_extract(meta, '$.title') AS title,
       substr(description, 1, 200) AS description
FROM findings
ORDER BY id;
```

For each likely duplicate, stop. Show its ID, repo, status, title and why it looks the
same, and offer a side-by-side comparison. When the user asks for one, fetch the full row
with `SELECT * FROM findings WHERE id = <id>;` and present the report and the tally
finding field by field. Leave the report out unless the user says it is not a
duplicate. An existing finding is edited in the web UI or with `/update-vulnerability`.

### 8. Get approval

Show the user:

- Reports skipped as already recorded (with finding IDs), and files skipped as indexes
- The repo for each report, and any split, multi-repo or repo-mismatch notes from step 4
- The duplicate check result, including related findings that are not duplicates
- One report: its full payload as formatted JSON in a `json` code block, without the
  report text (`jq 'del(.meta.source_report)' <payload>`), plus the report's path, size
  and checksum.
- Several reports: a table with code, repo, severity, confidence, CWE, OWASP category,
  `rule_id` and `file:line`, one full payload as formatted JSON as above, and the
  payloads directory so the user can open the rest.

Mark every value you chose rather than copied (severity, confidence, CWE, OWASP
category, `finding_type`, `rule_id`, `segment`, location) as your choice. Then stop and
wait. On changes, update the spec, run step 6 again and show the result again.

### 9. Record the findings

For each approved payload:

```bash
PYTHONNOUSERSITE=1 .venv/bin/python3 tally-cli.py --base-path . \
  --project <project> --command finding-add --repo <repo> \
  --finding-file <scratchpad>/ingest/payloads/<CODE>.json
```

On success the CLI prints `{"finding_id": <id>}`. Stop at the first failure and tell the
user which reports were recorded and which were not.

Confirm nothing was lost by writing the stored text back out and comparing checksums:

```bash
sqlite3 projects/<project>/sqlite/findings.db \
  "SELECT writefile('<scratchpad>/ingest/stored-<CODE>.txt',
     json_extract(meta, '$.source_report')) FROM findings WHERE id = <id>;"
sha256sum <report-path> <scratchpad>/ingest/stored-<CODE>.txt
```

The checksums must match. A mismatch means the stored text is incomplete: tell the user
and do not suggest deleting the report.

### 10. Update split parents

When the user approved it in step 4, append the note to each parent's description.
`finding-update` replaces the whole description, so read the current one first and pass
it back with the note added:

```bash
sqlite3 -readonly projects/<project>/sqlite/findings.db \
  "SELECT description FROM findings WHERE id = <parent_id>;"
PYTHONNOUSERSITE=1 .venv/bin/python3 tally-cli.py --base-path . \
  --project <project> --command finding-update --finding-id <parent_id> \
  --description "<current description>

Split into #<id> (<CODE>) and #<id> (<CODE>)."
```

### 11. Report

Leave scratchpad files in place. Present every recorded finding as
`#<id> <CODE> (<repo>)`, the skipped reports and files, any parent notes added, and:

```
Source reports stored verbatim: yes, all <n> checksums match

Use these IDs in Jira tickets, PRs and commit messages.
Do not include vulnerability details outside of tally.
```
