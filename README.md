# Tally

[![CI](https://github.com/scifeks/tally/actions/workflows/ci.yml/badge.svg)](https://github.com/scifeks/tally/actions/workflows/ci.yml)

Tally is a security auditing platform with a web UI and CLI for orchestrating scanners, triaging findings, and generating reports. It wraps common security tools, stores findings in a knowledge base (ChromaDB + configurable LLM), and lets you scan, triage, search, chat, and report from a browser or terminal.

## Features

- Browser-based UI with dashboard, scan launcher, findings editor, AI triage, report builder, and RAG chat
- Wraps tools like Semgrep, OWASP ZAP, XSStrike, Gitleaks, OSV-Scanner, and [more](docs/tools.md)
- AI triage: an LLM agent reads each finding and its source code, then produces a verdict with severity, confidence, remediation, and attack vector
- Four report formats: Markdown, HTML, JSON, and assembled PDF with LLM-drafted narrative sections
- RAG-powered search and chat over ingested findings using any configured provider ([docs/chat.md](docs/chat.md))
- Project-based isolation: each project has its own config, vector store, and outputs
- Automatic tool discovery on startup: skips tools that are not installed
- CLI REPL for terminal-based workflows and scripting
- Human-in-the-loop approval before each tool execution
- Docker execution support for all tools

## Requirements

- **Python 3.10+**
- **Node.js and npm** for the web UI frontend
- **Ollama** running locally (`ollama serve`) with a chat model and embedding model pulled. Required for ChromaDB embeddings and for any role configured to use the `"ollama"` provider. Can be skipped if all roles are set to `"claude"` and you manage embeddings separately, but the default configuration uses Ollama.
- **Anthropic API key**: required only when any role is set to `"claude"` in `config/global.json`. Set via `ANTHROPIC_API_KEY` environment variable or the `claude.api_key` config field.
- Linux or macOS
- System tools are optional. Tally skips tools that are not installed

## Quick Start

```bash
# 1. Install Python and Node.js dependencies
bash install.sh

# 2. Start Ollama (separate terminal)
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama serve

# 3. Edit global config (configure providers and feature inference blocks)
cp config/global-example.json config/global.json
# edit config/global.json: configure provider blocks (ollama, llama_cpp,
# or claude) and feature inference blocks (search_inference, chat_inference,
# report_inference, and embeddings_inference)

# 4. Start Tally (first run launches an interactive tool setup wizard)
.venv/bin/python3 tally.py

# 5. Create a project, add a repo, and run your first scan
project add
repo add
scan --tool=semgrep

# 6. Launch the web UI
ui serve
```

## Web UI

Run `ui serve` from the REPL to start the web UI. Tally opens your browser to a React SPA backed by a FastAPI server. The UI provides the full Tally workflow in a graphical interface:

- **Dashboard** with project stats, recent scans, and quick-action tiles
- **Findings** table with filtering, sorting, and inline editing of severity, status, remediation, and other fields
- **Scans** launcher with tool selection, real-time progress tracking, and saved scan configurations
- **Triage** runner with batch visualization and progress tracking
- **Reports** builder with draft generation, format selection, and download
- **Chat** with session history over your project's findings
- **Configuration** for projects, repositories, tool overrides, and argument templates
- **URL Lists** management for DAST scanning targets

See [docs/ui.md](docs/ui.md) for the full walkthrough.

## REPL Command Reference

The REPL provides the same capabilities as the web UI in a terminal interface. All commands below are also available through the browser.

### Project Management

| Command | Description |
|---|---|
| `project add` | Create a new project (interactive) |
| `project edit [<name>]` | Edit project-level settings (interactive) |
| `project list` | List all projects |
| `project switch <name>` | Switch active project |
| `project info` | Show active project details |
| `project delete <name>` | Delete a project and all its data |

### Repository Management

| Command | Description |
|---|---|
| `repo add` | Add a repository to the active project |
| `repo list` | List configured repositories |
| `repo edit <name>` | Edit a repository's configuration |
| `repo delete <name>` | Delete a repository from the project |

### Tool Management

| Command | Description |
|---|---|
| `tool add` | Add a tool to configuration (interactive) |
| `tool list` | List configured tools and their status |
| `tool edit <name>` | Edit tool configuration |
| `tool remove <name>` | Remove a tool from configuration |

### Scanning

| Command | Description |
|---|---|
| `scan` | Full scan: all configured tools across all repos |
| `scan --tool=<tool,...>` | Run one or more specific tools (comma-separated) |
| `scan --repo=<repo>` | Run all repo-appropriate tools on one repository |
| `scan --domain=<domain,...>` | Run all tools in one or more domains: `code`, `web` |
| `scan --skip-tools=<tool,...>` | Run all tools except the ones listed (comma-separated) |
| `scan --repo=<repo> --tool=<tool,...>` | Run specific tools on one repository |
| `scan --skip-enrichment` | Skip LLM enrichment; findings are persisted to ChromaDB without enrichment fields |
| `run <tool> [args...]` | Execute a tool with raw arguments |

### Knowledge Base

| Command | Description |
|---|---|
| `search [--flags...]` | Structured search over ingested findings (`search --help` for options) |
| `chat <message>` | RAG-augmented chat with the LLM |
| `stats` | Show knowledge base statistics |
| `purge` | Delete ALL findings, tool outputs, and reports |
| `purge --tool=<tool,...>` | Delete findings for specific tool(s) only; reports unaffected |
| `purge --keep-reports` | Delete all findings and tool outputs but keep generated reports |

### Web UI

| Command | Description |
|---|---|
| `ui serve` | Start the FastAPI + Vite dev server and open the web UI |
| `ui serve --stop` | Stop the running web servers |

### Triage

| Command | Description |
|---|---|
| `triage` | Run AI triage on untriaged SAST and API findings for the active project |
| `triage --batch` | Run batching phase only, no agent invocation |
| `triage --dry-run` | Batch + render prompts to DEBUG log, no agent invocation |
| `triage --rebuild-container` | Stop containers and rebuild the triage agent Docker image |

### Reporting

| Command | Description |
|---|---|
| `report` | Assemble and generate full PDF report (default) |
| `report --format=<fmt>` | Output format: `pdf` (default), `markdown`, `html`, `json` |
| `report --testing-type <type>` | Engagement type: `white_box` (default), `grey_box`, `black_box` |
| `report --engagement-date <YYYY-MM-DD>` | Engagement date shown in the report |
| `report --output=<path>` | Write report to a specific file path |
| `report draft` | Generate LLM drafts for all six report sections |
| `report draft <section>` | Generate a draft for one section only |
| `report draft <section> --force` | Overwrite an existing draft without prompting |
| `report draft --skip-triage` | Include all findings regardless of triage status |
| `report shell` | Render a shell PDF for visual layout inspection |
| `report shell --output <path>` | Write shell PDF to a specific file path |

See [docs/report.md](docs/report.md) for the full PDF assembly workflow and argument reference.

### Integrations

| Command | Description |
|---|---|
| `export defectdojo` | Export all findings to DefectDojo |
| `export defectdojo --run-id=<id>` | Export findings from a specific scan run |
| `export defectdojo --test-connection` | Verify DefectDojo connectivity and authentication |

See [docs/integrations/defect-dojo.md](docs/integrations/defect-dojo.md) for setup and configuration.

### Utility

| Command | Description |
|---|---|
| `help` | Show command reference |
| `clear` | Clear the screen |
| `exit` / `quit` | Exit Tally |

## Docker Support

Tools can run locally or inside a Docker container. The execution mode is configured per-tool in `config/commands.json`.

**Local execution.** Tally runs the tool binary directly:

```json
{
  "semgrep": {
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/semgrep"
  }
}
```

**Docker execution.** Tally uses `docker exec` to run the tool inside a running container:

```json
{
  "semgrep": {
    "type": "repo",
    "location": "docker",
    "container": {
      "name": "semgrep-container",
      "tool_path": "/usr/local/bin/semgrep"
    }
  }
}
```

`config/commands.json` is auto-generated on first run via an interactive setup wizard. Use `tool edit <name>` to change a tool's execution mode at any time.

## Startup Flags

```bash
.venv/bin/python3 tally.py --check        # Check dependencies and exit
.venv/bin/python3 tally.py --skip-checks  # Skip dependency check (development)
```

## Documentation

- [docs/usage.md](docs/usage.md) - Full REPL usage guide with examples
- [docs/cli.md](docs/cli.md) - CLI reference for scripted and automated workflows
- [docs/ui.md](docs/ui.md) - Web UI walkthrough: dashboard, findings, scans, triage, reports, chat, and configuration
- [docs/report.md](docs/report.md) - Report generation guide: quick reports, PDF assembly, and shell preview
- [docs/chat.md](docs/chat.md) - RAG chat configuration and usage
- [docs/triage.md](docs/triage.md) - AI triage: setup, container lifecycle, and security model
- [docs/configuration.md](docs/configuration.md) - Config file reference
- [docs/tools.md](docs/tools.md) - Supported tools and how each is detected at startup
- [docs/url-discovery.md](docs/url-discovery.md) - URL discovery pipeline: Katana, Noir, user-provided endpoint files, auth, merging, and downstream consumers
- [docs/endpoint-files.md](docs/endpoint-files.md) - Supplying your own OAS3/Swagger/Postman/HAR endpoint file
- [docs/endpoint-file-adapter-internals.md](docs/endpoint-file-adapter-internals.md) - Developer guide for adding endpoint file format adapters
- [docs/adding-tool-wrappers.md](docs/adding-tool-wrappers.md) - Developer guide for adding tool wrappers (requires `config/commands.json` registration to take effect)
- [docs/integrations/defect-dojo.md](docs/integrations/defect-dojo.md) - DefectDojo integration: export findings, configuration, and field mapping
- [docs/docker.md](docs/docker.md) - Optional Docker containers for npm-audit and composer-audit
- [docs/restrictions.md](docs/restrictions.md) - Legal restrictions

## Known Limitations

### Noir framework support

Noir does not support every web framework. It is skipped automatically for:

- **Node.js apps.** Noir's JavaScript parser has a known defect that causes it
  to loop indefinitely on complex Node.js codebases. Tally detects Node.js apps
  automatically by the presence of `package.json` at the repo root and skips
  Noir for them.
- **Unsupported Python frameworks.** aiohttp, bottle, cherrypy, falcon, and
  pyramid are not recognized by Noir v0.25.1. Tally detects them via the
  repository's `dependencies_file` and skips Noir automatically.

When Noir is skipped, ZAP falls back to spider-only discovery mode. You can
supply a user-provided OAS3, OAS2/Swagger, Postman collection, or HAR file
via `repo add` / `repo edit` to give ZAP accurate endpoint coverage regardless
of Noir support.

See [docs/url-discovery.md](docs/url-discovery.md) for the full discovery
pipeline and [docs/endpoint-files.md](docs/endpoint-files.md) for endpoint file
setup.

## Legal Notice (California and Colorado)

This software is **not intended for use in the States of California or Colorado**.

Recent legislation, including **California Assembly Bill AB 1043 (Digital Age Assurance Act)** and **Colorado Senate Bill SB26-051 (Age Attestation on Computing Devices)**, establishes frameworks in which operating systems collect a user's age or birth date and expose an **age-bracket signal via an API**. Under these frameworks, **applications are required to request this signal when an application is downloaded or launched**.

This project does **not implement functionality to request or process operating-system age signals**, and the maintainers do not intend to add such functionality.

If you are located in **California or Colorado**, **do not download, run, or use this software**.

Users are responsible for ensuring that their use of this software complies with the laws applicable in their jurisdiction.

See the full policy here:  
[docs/restrictions.md](docs/restrictions.md)

## License

GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for details.
