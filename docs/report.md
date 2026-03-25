# Report Generation

Tally's report pipeline generates professional penetration testing reports in two modes: **quick text reports** (Markdown, HTML, or JSON) built directly from the findings database, and a **full PDF report** assembled from LLM-drafted narrative sections and structured findings data.

The `report` command defaults to PDF assembly — the full client-deliverable report.

---

## Quick Text Reports

To generate a structured text report instead of a PDF, pass `--format`:

```
[acme-audit]> report --format=markdown
[acme-audit]> report --format=html
[acme-audit]> report --format=json --output=/tmp/acme-findings.json
```

### Arguments

| Argument | Description |
|---|---|
| `--format=<fmt>` | Output format: `pdf` (default), `markdown`, `html`, `json` |
| `--output=<path>` | Write the report to a specific file path |

When no `--output` path is provided, the file is written to `projects/<project>/reports/` with a timestamp in the filename.

---

## PDF Assembly Workflow

The PDF report is a formatted document suitable for client delivery. It includes narrative prose written by an LLM based on your findings, structured findings tables, an attack surface overview, severity distribution charts, and a glossary.

Assembly is a four-step process.

### Step 1 — Triage your findings

LLM draft generation reads only findings that have been triaged and marked for inclusion in the report. Run triage before generating any drafts:

```
[acme-audit]> triage
```

See [docs/mcp.md](mcp.md) for the full triage guide.

If you want to generate drafts before triage is complete (e.g. for development or preview),
pass `--skip-triage` to `report draft` — see [Step 2](#step-2--generate-llm-drafts) below.

### Step 2 — Generate LLM drafts

Run `report draft` with no arguments to generate all six report sections in sequence:

```
[acme-audit]> report draft
```

To generate or regenerate a single section:

```
[acme-audit]> report draft risk-level
```

If a draft file already exists, Tally asks before overwriting. Pass `--force` to skip the prompt:

```
[acme-audit]> report draft risk-level --force
```

To generate drafts without requiring triage (all findings are included regardless of triage
status):

```
[acme-audit]> report draft --skip-triage
```

### `report draft` Arguments

| Argument | Description |
|---|---|
| `<section>` | Generate only the named section (omit to generate all six) |
| `--force` | Overwrite an existing draft without prompting |
| `--skip-triage` | Include all findings regardless of triage status |

The six sections, in generation order:

| Section | Description |
|---|---|
| `executive-summary` | 2–3 paragraph non-technical summary for a management audience |
| `risk-level` | Single paragraph stating the overall risk rating and rationale |
| `critical-issues` | Top 3–5 critical findings described in plain English |
| `improvement-points` | Recurring vulnerability themes and patterns across the codebase |
| `scope-and-methodology` | What was tested, which tools were used, and how |
| `general-recommendations` | Actionable recommendations grouped by theme |

> **Note:** `general-recommendations` reads the `improvement-points` draft as context. When regenerating sections individually, always regenerate `improvement-points` before `general-recommendations`.

Draft files are saved to `projects/<project>/reports/draft/<section>.md`.

### Step 3 — Review drafts

Open the draft files in any editor and make corrections. When a section is ready for assembly, copy or move it to the `reviewed/` directory:

```bash
cp projects/acme-audit/reports/draft/executive-summary.md \
   projects/acme-audit/reports/reviewed/executive-summary.md
```

During assembly, Tally checks `reviewed/` first. If a reviewed file exists it is used silently. If only a draft file exists, Tally asks whether to proceed with the unreviewed version. If neither file exists, assembly stops with an error.

### Step 4 — Assemble the PDF

Run `report` to produce the final PDF:

```
[acme-audit]> report
```

If any of the six sections have not been drafted yet, Tally lists the missing sections and instructs you to run `report draft` first.

By default the PDF is written to `projects/<project>/reports/<project>-report.pdf`. If the file already exists, Tally asks before overwriting.

#### Arguments

| Argument | Description |
|---|---|
| `--testing-type <type>` | Engagement type: `white_box` (default), `grey_box`, or `black_box` |
| `--engagement-date <YYYY-MM-DD>` | Engagement date shown in the report (defaults to the project creation date) |
| `--output <path>` | Write the PDF to a specific file path |

The company name shown in the report is read from the project's `company_name` field. Set it with `project add` (during creation) or `project edit` (afterwards).

#### Examples

```
[acme-audit]> report

[acme-audit]> report --testing-type grey_box

[acme-audit]> report --engagement-date 2025-03-01

[acme-audit]> report --output /tmp/acme-final.pdf
```

You can also pass `--format=pdf` explicitly, which is equivalent to the default:

```
[acme-audit]> report --format=pdf
```

---

## Shell PDF

`report shell` renders a PDF with the same layout and narrative sections as `report` but without any findings content. The attack surface overview, findings tables, and severity charts are replaced with placeholder blocks.

This command is intended for developers customizing the report's visual appearance. Use it when adjusting CSS styles, page layout, typography, or template markup. Because the shell skips database queries for findings content, it renders faster than a full assembly — making it practical to iterate quickly on the visual design.

### Arguments

| Argument | Description |
|---|---|
| `--testing-type <type>` | Engagement type: `white_box` (default), `grey_box`, `black_box` |
| `--engagement-date <YYYY-MM-DD>` | Engagement date (defaults to the project creation date) |
| `--output <path>` | Write the shell PDF to a specific path (default: `/tmp/tally_shell_report.pdf`) |

### Examples

```
[acme-audit]> report shell

[acme-audit]> report shell --output /tmp/layout-check.pdf

[acme-audit]> report shell --testing-type black_box
```

---

## File Layout

All report-related files for a project live under `projects/<project>/reports/`:

```
projects/acme-audit/reports/
  draft/
    executive-summary.md       # LLM-generated, pending review
    risk-level.md
    critical-issues.md
    improvement-points.md
    scope-and-methodology.md
    general-recommendations.md
  reviewed/
    executive-summary.md       # Human-edited; takes precedence over draft/
  acme-audit-report.pdf        # Final assembled PDF
  report_2025-03-21_142301.md  # Quick text report (Markdown)
  report_2025-03-21_143012.html
```

Files in `reviewed/` always take precedence over `draft/` during assembly. A section with no file in either directory causes assembly to stop with an error.
