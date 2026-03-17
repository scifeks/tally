# Tally

[![CI](https://github.com/scifeks/tally/actions/workflows/ci.yml/badge.svg)](https://github.com/scifeks/tally/actions/workflows/ci.yml)

Tally is a CLI REPL for orchestrating web application penetration testing. It wraps common security tools, stores findings in a RAG knowledge base (ChromaDB + Ollama), and lets you search, chat over, and report on findings — all within a single terminal session.

## Features

- Wraps tools like nmap, OWASP ZAP, OSV-Scanner, and [more](docs/tools.md)
- Project-based isolation: each project has its own config, vector store, and outputs
- Automatic tool discovery on startup — skips tools that are not installed
- RAG-powered search and chat over ingested findings — backed by Ollama or Anthropic Claude
- Three report formats: Markdown, HTML, JSON
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
| `project list` | List all projects |
| `project switch <name>` | Switch active project |
| `project info` | Show active project details |

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
| `scan --type=<type,...>` | Run all tools of one or more types |
| `scan --repo=<repo> --tool=<tool,...>` | Run specific tools on one repository |
| `run <tool> [args...]` | Execute a tool with raw arguments |

### Knowledge Base

| Command | Description                                                            |
|---|------------------------------------------------------------------------|
| `search [--flags...]` | Structured search over ingested findings (`search --help` for options) |
| `chat <message>` | RAG-augmented chat with the LLM                                        |
| `stats` | Show knowledge base statistics                                         |
| `purge --tool=<tool,...>` | Delete findings from one or more tools (comma-separated)               |

### Reporting

| Command | Description |
|---|---|
| `report` | Generate Markdown report (saved to projects/[name]/reports/) |
| `report --format html` | Generate HTML report |
| `report --format json` | Generate JSON report |
| `report --output <path>` | Write report to a specific path |

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
- [docs/mcp.md](docs/mcp.md) — MCP triage system setup and usage guide
- [docs/configuration.md](docs/configuration.md) — Config file reference
- [docs/tools.md](docs/tools.md) — Supported tools and how each is detected at startup
- [docs/adding-tool-wrappers.md](docs/adding-tool-wrappers.md) — Developer guide for adding tool wrappers
- [docs/docker.md](docs/docker.md) — Usage instructions for optional Docker containers
- [docs/restrictions.md](docs/restrictions.md) - Legal restrictions

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
