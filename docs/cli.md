# CLI

Tally's CLI (`tally-cli.py`) is a non-interactive entry point that exposes the same scanning, reporting, and triage capabilities as the REPL, but driven by command-line arguments instead of a prompt loop. It is designed for automation: crontab schedules, CI pipelines, pre-commit hooks, and scripted workflows. All confirmation prompts are auto-approved, so the CLI never blocks waiting for input.

---

## Prerequisites

Before using the CLI, you must complete the location attestation once through the interactive REPL (`python3 tally.py`). The CLI checks this attestation on every invocation and exits with code 1 if it has not been confirmed. See [docs/usage.md](usage.md) for REPL setup instructions.

You also need at least one project created through the REPL or web UI before the CLI can operate on it.

---

## Global Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--command COMMAND` | string | *(required)* | Command to execute: `scan`, `run`, `report`, `triage`, `purge`, `stats`, `integration-sync`, `ui` |
| `--base-path DIR` | string | `.` | Base directory for projects |
| `--project NAME` | string | *(required)* | Target project name |

`--project` is required for all commands except `--command ui` and `--command triage --rebuild-container`.

---

## Commands

### scan

Run security scans across one or more repositories.

```
tally --project NAME --command scan [--repo REPOS] [--tool TOOLS | --skip-tools TOOLS]
                                    [--domain DOMAINS] [--skip-enrichment]
```

| Flag | Description |
|------|-------------|
| `--repo REPOS` | Comma-separated repository names to scan |
| `--tool TOOLS` | Comma-separated tools to use (overrides defaults) |
| `--skip-tools TOOLS` | Comma-separated tools to exclude |
| `--domain DOMAINS` | Comma-separated domains (for DAST tools) |
| `--skip-enrichment` | Skip finding enrichment after scanning |

`--tool` and `--skip-tools` are mutually exclusive. Repository, tool, and domain names are validated against the project configuration; unknown names exit with code 2.

A scan exits 0 when it completes, even if individual tools within the scan encounter errors. Exit 1 means the scan itself could not run (e.g., another scan is already in progress).

```bash
# Scan all repos with all configured tools
python3 tally-cli.py --project myapp --command scan

# Scan specific repos with specific tools, skip enrichment
python3 tally-cli.py --project myapp --command scan --repo backend,api --tool semgrep,gitleaks --skip-enrichment

# Scan everything except bandit
python3 tally-cli.py --project myapp --command scan --skip-tools bandit
```

### run

Execute a single tool directly with optional arguments.

```
tally --project NAME --command run --tool TOOL [--timeout SECONDS] [-- ARGS...]
```

| Flag | Description |
|------|-------------|
| `--tool TOOL` | Tool name (required) |
| `--timeout SECONDS` | Execution timeout |
| `ARGS...` | Raw arguments passed through to the tool (after `--`) |

The tool name is looked up case-insensitively. If the tool is not installed, the command exits with code 1. Output file paths are printed to stdout on success.

```bash
# Run semgrep with default settings
python3 tally-cli.py --project myapp --command run --tool semgrep

# Run with a timeout and custom arguments
python3 tally-cli.py --project myapp --command run --tool semgrep --timeout 120 -- --config=p/owasp-top-10
```

### report

Generate security reports. Use `--type` to select the report mode: `final` (default), `draft`, or `shell`.

```
tally --project NAME --command report [--type TYPE] [--format FORMAT] [--output PATH]
                                      [--testing-type TYPE] [--engagement-date DATE]
                                      [--section SECTION] [--force] [--skip-triage]
```

**Main report flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--type TYPE` | `final` | Report mode: `final`, `draft`, `shell` |
| `--format FORMAT` | `pdf` | Output format: `pdf`, `markdown`, `html`, `json` |
| `--output PATH` | auto-generated | Output file path |
| `--testing-type TYPE` | `white_box` | `white_box`, `grey_box`, or `black_box` |
| `--engagement-date DATE` | none | Date in `YYYY-MM-DD` format |

**PDF reports** require all sections to be drafted first. Run `--command report --type draft` before `--command report --format pdf`. Markdown, HTML, and JSON reports are generated via the RAG engine and do not require drafts.

**Draft flags** (used with `--type draft`):

| Flag | Description |
|------|-------------|
| `--section SECTION` | Section name (omit to draft all sections) |
| `--force` | Overwrite existing drafts |
| `--skip-triage` | Skip triage before drafting |

**Shell mode** (`--type shell`) generates a PDF with placeholder sections. Useful for previewing layout before drafting content.

```bash
# Draft all report sections
python3 tally-cli.py --project myapp --command report --type draft

# Draft a single section, overwriting any existing draft
python3 tally-cli.py --project myapp --command report --type draft --section executive_summary --force

# Generate the final PDF
python3 tally-cli.py --project myapp --command report --output ./report.pdf

# Generate a markdown report
python3 tally-cli.py --project myapp --command report --format markdown

# Generate a shell PDF to preview layout
python3 tally-cli.py --project myapp --command report --type shell --engagement-date 2025-06-01
```

### triage

Classify and score findings using an LLM agent.

```
tally --project NAME --command triage [--batch] [--dry-run]
tally --command triage --rebuild-container
```

| Flag | Description |
|------|-------------|
| `--batch` | Create triage batches without invoking the agent (no Docker required) |
| `--dry-run` | Render batch prompts to the debug log without executing |
| `--rebuild-container` | Stop containers, rebuild the triage image, and exit |

Full triage (no flags) requires Docker. It builds the triage agent image if needed, starts containers, and runs triage sessions against untriaged findings. Batch mode prepares the batches without running the agent. Dry-run mode writes the rendered prompts to the debug log for inspection.

`--rebuild-container` does not require `--project`.

```bash
# Full triage with Docker
python3 tally-cli.py --project myapp --command triage

# Batch mode (no Docker)
python3 tally-cli.py --project myapp --command triage --batch

# Rebuild the triage container image
python3 tally-cli.py --command triage --rebuild-container
```

### purge

Delete findings from the knowledge base and optionally from disk.

```
tally --project NAME --command purge [--tool TOOLS] [--keep-reports]
```

| Flag | Description |
|------|-------------|
| `--tool TOOLS` | Comma-separated tools to purge (omit to purge everything) |
| `--keep-reports` | Preserve generated reports (only applies to full purge) |

When `--tool` is specified, only findings and tool output files for those tools are deleted. When omitted, all findings, chat sessions, URL findings, tool outputs, and reports are deleted. Use `--keep-reports` on a full purge to retain reports.

```bash
# Purge findings from specific tools
python3 tally-cli.py --project myapp --command purge --tool semgrep,gitleaks

# Purge everything but keep reports
python3 tally-cli.py --project myapp --command purge --keep-reports

# Full purge
python3 tally-cli.py --project myapp --command purge
```

### stats

Display knowledge base statistics for a project.

```
tally --project NAME --command stats
```

No additional flags. Prints total document count, breakdown by tool, breakdown by severity (if available), and the last ingestion timestamp. Exits with code 1 if the RAG engine is unavailable.

```bash
python3 tally-cli.py --project myapp --command stats
```

### integration-sync

Export findings to configured integrations. Currently supports DefectDojo.

```
tally --project NAME --command integration-sync [--run-id ID]
```

| Flag | Description |
|------|-------------|
| `--run-id ID` | Export findings from a specific scan run only |

Requires DefectDojo connection settings in `config/global.json` and targeting settings in the project's `project.json`. See [docs/integrations/defect-dojo.md](integrations/defect-dojo.md) for configuration.

Exits 0 on success, 1 if the integration is not configured or the export fails, 3 if the project is not found.

```bash
# Export all findings to DefectDojo
python3 tally-cli.py --project myapp --command integration-sync

# Export findings from a specific scan run
python3 tally-cli.py --project myapp --command integration-sync --run-id 5
```

### ui

Launch the web interface.

```
tally --command ui
```

Does not require `--project`. Starts the API server and frontend dev server, then blocks until interrupted (Ctrl+C). Host, port, and Vite port are read from the global configuration.

```bash
python3 tally-cli.py --command ui
```

---

## Exit Codes

Every command exits with a numeric code you can check in scripts and CI pipelines.

| Code | Name | Meaning |
|------|------|---------|
| 0 | Success | Command completed without errors |
| 1 | General error | Unexpected failure, I/O error, or service unavailable |
| 2 | Invalid arguments | Mutually exclusive flags, unknown tool or repo names, bad values |
| 3 | Project not found | `--project` not specified or the named project does not exist |

Ctrl+C produces exit code 130.

### When each code applies

**Exit 0.** The command ran to completion. For `scan`, all requested tools executed (individual tool failures within a scan do not change the exit code). For `purge`, deletion completed. For `stats`, statistics were printed.

**Exit 1.** Covers runtime failures that are not argument or project errors: RAG engine unavailable, scan already in progress, Docker not available, PDF rendering failure, or unexpected exceptions.

**Exit 2.** The arguments are syntactically valid but semantically wrong: `--tool` and `--skip-tools` both specified on `scan`, unknown tool/repo/domain names.

**Exit 3.** The `--project` flag was omitted on a command that requires it, the project does not exist, or the project has been archived.

---

## Automation Examples

### Scheduled scans with crontab

Run a nightly scan at midnight and log the output:

```bash
0 0 * * * cd /opt/tally && .venv/bin/python3 tally-cli.py --project myapp --command scan >> /var/log/tally-scan.log 2>&1
```

Sync findings to DefectDojo every 6 hours:

```bash
0 */6 * * * cd /opt/tally && .venv/bin/python3 tally-cli.py --project myapp --command integration-sync >> /var/log/tally-sync.log 2>&1
```

Weekly report generation every Friday at 6 PM:

```bash
0 18 * * 5 cd /opt/tally && .venv/bin/python3 tally-cli.py --project myapp --command report --type draft --skip-triage && .venv/bin/python3 tally-cli.py --project myapp --command report --output /opt/reports/weekly.pdf >> /var/log/tally-report.log 2>&1
```

### CI pipeline

Check exit codes to gate pipeline stages. A scan that completes is exit 0, regardless of whether individual tools found vulnerabilities. Use `stats` or the web UI to inspect results after the scan.

```bash
#!/bin/bash
set -e

python3 tally-cli.py --project "$PROJECT" --command scan --skip-enrichment
if [ $? -ne 0 ]; then
    echo "Scan failed" >&2
    exit 1
fi

python3 tally-cli.py --project "$PROJECT" --command triage --batch
python3 tally-cli.py --project "$PROJECT" --command report --format json --output findings.json
```

Handle specific exit codes when you need different behavior for argument errors vs. runtime failures:

```bash
python3 tally-cli.py --project "$PROJECT" --command scan --tool semgrep
rc=$?
case $rc in
    0) echo "Scan complete" ;;
    2) echo "Bad arguments; check tool names" >&2; exit 1 ;;
    3) echo "Project not found" >&2; exit 1 ;;
    *) echo "Scan failed (exit $rc)" >&2; exit 1 ;;
esac
```

### Pre-commit hook

Run a fast single-tool scan before each commit. Place this in `.git/hooks/pre-commit`:

```bash
#!/bin/bash
python3 /opt/tally/tally-cli.py --project myapp --command run --tool gitleaks --timeout 30
if [ $? -ne 0 ]; then
    echo "gitleaks check failed; commit aborted" >&2
    exit 1
fi
```

### Scripted workflows

Chain multiple commands with exit code checks between steps:

```bash
#!/bin/bash
set -e

PROJECT="myapp"
TALLY="python3 /opt/tally/tally-cli.py --project $PROJECT"

# Purge stale data, scan, triage, and generate a report
$TALLY --command purge --keep-reports
$TALLY --command scan
$TALLY --command triage --batch
$TALLY --command report --type draft --force --skip-triage
$TALLY --command report --output /opt/reports/full-report.pdf

echo "Pipeline complete"
```

---

## Differences from the REPL

| Behavior | REPL | CLI |
|----------|------|-----|
| Command syntax | `scan --tool semgrep` | `--command scan --tool semgrep` |
| Confirmation prompts | Asks interactively | Auto-approves all |
| Project selection | Set once with `project use` | `--project` flag on every invocation |
| Location attestation | Completed during first run | Must already be confirmed |
| Output formatting | Rich terminal markup | Plain text |
| Tool discovery wizard | Interactive setup on first run | Reads existing `config/commands.json` |
