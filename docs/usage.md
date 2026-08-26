# Usage Guide

Tally has three interfaces. Each serves a different workflow. All three share the same scanning, triage, reporting, and chat capabilities, but differ in how you interact with them.

---

## Web UI (recommended)

The web UI is a browser-based dashboard for interactive security audits. It is the most complete interface, with features that have no REPL or CLI equivalent: visual scan progress, drag-and-drop configuration, bulk finding actions, saved scan templates, and multi-session chat history.

Use the web UI when you are running an audit interactively and have browser access on the host.

**What you get:**

- **Dashboard** with project stats, recent scans, and high-severity finding alerts
- **Findings browser** with segment tabs, severity filters, full-text search, bulk actions, and an inline detail panel for editing findings
- **Scans page** with advanced options (repos, tools, domains, argument profiles), saved scan templates, and a real-time event log
- **Triage page** with batch progress visualization, resume from failure, and prompt injection warnings
- **Reports page** with per-section draft cards (generate, review, upload), format selection, and report history with downloads
- **Chat** with persistent multi-turn sessions, streaming responses, and session management
- **Configuration page** for managing repositories, tool overrides, argument templates, and file uploads

**Launching:**

From the REPL:

```
[no-project]> ui serve
```

From the CLI:

```bash
python3 tally-cli.py --command ui
```

See [web-ui.md](web-ui.md) for the full page-by-page walkthrough.

---

## REPL

The REPL is an interactive terminal interface. Use it when a browser is unavailable or inappropriate: SSH sessions, remote servers, headless environments, or client-sensitive audits where browser exposure is a concern.

The REPL provides the same scanning, triage, reporting, and chat capabilities as the web UI, but through text commands. Some differences:

- Chat is single-shot (one question, one answer). The web UI supports persistent multi-turn sessions.
- Configuration is done through interactive prompts (`repo add`, `tool edit`) rather than a graphical form.
- Scan progress and triage results display as terminal output rather than visual dashboards.

**Starting:**

```bash
.venv/bin/python3 tally.py
```

See [repl.md](repl.md) for commands and terminal workflows.

---

## CLI

The CLI is a non-interactive entry point for automation. Use it for cron jobs, CI pipelines, pre-commit hooks, and scripted workflows. All confirmation prompts are auto-approved, so the CLI never blocks waiting for input.

**Key differences from the REPL:**

- Every command requires `--project` and `--command` flags
- No interactive prompts; all options are passed as flags
- Exit codes (0, 1, 2, 3) are designed for scripting
- Project creation and initial setup must be done through the REPL or web UI first

**Example:**

```bash
python3 tally-cli.py --project myapp --command scan --tool semgrep --skip-enrichment
```

See [cli.md](cli.md) for all flags, exit codes, and automation examples.

---

## Common Workflows

### First-time setup

1. Install dependencies: `bash install.sh`
2. Configure your LLM provider in `config/global.json`. See [llm-providers.md](llm-providers.md).
3. Start Tally: `.venv/bin/python3 tally.py`
4. Create a project: `project add`
5. Add a repository: `repo add`
6. Run your first scan: `scan --tool=semgrep`
7. Launch the web UI: `ui serve`

After initial setup, most users work primarily through the web UI.

### Scanning

| Interface | How to scan |
|---|---|
| Web UI | Open the Scans page, configure advanced options if needed, click Start. Progress streams in real time. Or click the orange Burp button to run a Burp crawl-and-audit scan (when configured). |
| REPL | `scan` for a full scan, or `scan --tool=semgrep --repo=backend` to scope it. Tally prompts before each tool runs. Use `burp scan` to run a Burp crawl-and-audit scan with an optional config name. |
| CLI | `python3 tally-cli.py --project myapp --command scan`. All prompts auto-approved. |

Burp scans require Burp Suite Professional running with REST API enabled and a `burp` section configured in `config/global.json`.

### Triage

| Interface | How to triage |
|---|---|
| Web UI | Open the Triage page, click Start Triage. Batch progress and verdicts stream in real time. Resume from failure with one click. |
| REPL | `triage`. Prompts for confirmation, then runs all untriaged findings. |
| CLI | `python3 tally-cli.py --project myapp --command triage`. |

### Reporting

| Interface | How to generate reports |
|---|---|
| Web UI | Open the Reports page, generate draft sections individually or in batch, select format and options, click Generate. Download from the history tab. |
| REPL | `report draft` to generate sections, `report` to assemble a PDF. `report --format=html` for other formats. |
| CLI | `python3 tally-cli.py --project myapp --command report --type draft` then `--command report --format pdf`. |

### Chat

| Interface | How to chat |
|---|---|
| Web UI | Open the Chat page. Create sessions, ask questions, get streaming answers grounded in your findings. Sessions persist across page visits. |
| REPL | `chat <question>`. Single-shot: one question, one answer. No session history. |
| CLI | Not available. Chat requires interactive input. |
