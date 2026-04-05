# Tally

[![CI](https://github.com/scifeks/tally/actions/workflows/ci.yml/badge.svg)](https://github.com/scifeks/tally/actions/workflows/ci.yml)

Tally is a CLI REPL for orchestrating web application security auditing. It wraps common security tools, stores findings in a RAG knowledge base (ChromaDB + Ollama), and lets you search, chat over, and report on findings — all within a single terminal session.

## Features

- Wraps tools like Semgrep, OWASP ZAP, Gitleaks, OSV-Scanner, and [more](docs/tools.md)
- Project-based isolation: each project has its own config, vector store, and outputs
- Automatic tool discovery on startup — skips tools that are not installed
- RAG-powered search and chat over ingested findings — backed by Ollama or Anthropic Claude
- Four report formats: Markdown, HTML, JSON, and assembled PDF with LLM-drafted narrative sections
- Browser-based findings reviewer with inline editing — launched on demand from the REPL
- Human-in-the-loop approval before each tool execution
- Dependency checker validates required packages on every startup
- Docker execution support for all tools

## Requirements

- **Python 3.10+**
- **Ollama** running locally (`ollama serve`) with a chat model and embedding model pulled — required for ChromaDB embeddings and for any role configured to use the `"ollama"` provider. Can be skipped if all three roles are set to `"claude"` and you manage embeddings separately, but the default configuration uses Ollama.
- **Anthropic API key** — required only when any role is set to `"claude"` in `config/global.json`. Set via `ANTHROPIC_API_KEY` environment variable or the `claude.api_key` config field.
- Linux or macOS
- System tools are optional — Tally skips tools that are not installed

## Quick Start

```bash
# 1. Install Python dependencies
bash install.sh

# 2. Start Ollama (separate terminal)
ollama pull qwen3:14b
ollama pull nomic-embed-text
ollama serve

# 3. Edit global config (set your LLM provider and models)
cp config/global-example.json config/global.json
# edit config/global.json — set ollama.model, ollama_embedding.model,
# and optionally switch any role to "claude" (requires ANTHROPIC_API_KEY)

# 4. Start Tally — first run launches an interactive tool setup wizard
.venv/bin/python3 tally.py

# 5. Create a project and start scanning
project add
repo add
scan --tool=semgrep
report
```

## REPL Command Reference

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
| `run <tool> [args...]` | Execute a tool with raw arguments |

### Knowledge Base

| Command | Description                                                            |
|---|------------------------------------------------------------------------|
| `search [--flags...]` | Structured search over ingested findings (`search --help` for options) |
| `chat <message>` | RAG-augmented chat with the LLM                                        |
| `stats` | Show knowledge base statistics                                         |
| `purge` | Delete ALL findings, tool outputs, and reports |
| `purge --tool=<tool,...>` | Delete findings for specific tool(s) only — reports unaffected |
| `purge --keep-reports` | Delete all findings and tool outputs but keep generated reports |

### Findings Visualizer

| Command | Description |
|---|---|
| `findings visualize` | Start the local findings browser and open it in your default browser |
| `findings visualize --stop` | Stop the running web server |

### Triage

| Command | Description |
|---|---|
| `triage` | Run AI triage on untriaged findings for the active project |
| `triage --batch` | Run batching phase only — no Claude sessions |
| `triage --dry-run` | Batch + render prompts to DEBUG log — no MCP server, no Claude |

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

### Utility

| Command | Description |
|---|---|
| `help` | Show command reference |
| `clear` | Clear the screen |
| `exit` / `quit` | Exit Tally |

## Docker Support

Tools can run locally or inside a Docker container. The execution mode is configured per-tool in `config/commands.json`.

**Local execution** — Tally runs the tool binary directly:

```json
{
  "semgrep": {
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/semgrep"
  }
}
```

**Docker execution** — Tally uses `docker exec` to run the tool inside a running container:

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

- [docs/usage.md](docs/usage.md) — Full usage guide with examples
- [docs/report.md](docs/report.md) — Report generation guide: quick reports, PDF assembly, and shell preview
- [docs/mcp.md](docs/mcp.md) — MCP triage system setup and usage guide
- [docs/findings-visualize.md](docs/findings-visualize.md) — Findings visualizer: browser-based findings browser with inline editing
- [docs/configuration.md](docs/configuration.md) — Config file reference
- [docs/tools.md](docs/tools.md) — Supported tools and how each is detected at startup
- [docs/adding-tool-wrappers.md](docs/adding-tool-wrappers.md) — Developer guide for adding tool wrappers
- [docs/docker.md](docs/docker.md) — Security Audit Containers
- [docs/restrictions.md](docs/restrictions.md) — Legal restrictions

## Known Limitations

### Noir on Node.js repositories

OWASP Noir has a known defect in its JavaScript parser that causes it to loop
indefinitely on complex Node.js codebases and produce no output. Tally works
around this by letting you mark a repository as a Node.js app during
`repo add` / `repo edit`. When marked, Noir is skipped for that repository
across all scan types and ZAP falls back to quickscan (spider-only) mode.

**Planned:** A future release will allow configuring a path to a pre-existing
OAS3, OAS2/Swagger, or Postman collection file on the repository so that ZAP
can use it in place of a Noir-generated spec — bypassing Noir entirely for
Node.js apps and for projects that already maintain an API spec.

See [docs/tools.md](docs/tools.md) for details.

## Legal Notice (California and Colorado)

This software is **not intended for use in the States of California or Colorado**.

Recent legislation — including **California Assembly Bill AB 1043 (Digital Age Assurance Act)** and **Colorado Senate Bill SB26-051 (Age Attestation on Computing Devices)** — establishes frameworks in which operating systems collect a user's age or birth date and expose an **age-bracket signal via an API**. Under these frameworks, **applications are required to request this signal when an application is downloaded or launched**.

This project does **not implement functionality to request or process operating-system age signals**, and the maintainers do not intend to add such functionality.

If you are located in **California or Colorado**, **do not download, run, or use this software**.

Users are responsible for ensuring that their use of this software complies with the laws applicable in their jurisdiction.

See the full policy here:  
[docs/restrictions.md](docs/restrictions.md)

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.
