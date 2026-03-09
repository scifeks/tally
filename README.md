# Tally

[![CI](https://github.com/scifeks/tally/actions/workflows/ci.yml/badge.svg)](https://github.com/scifeks/tally/actions/workflows/ci.yml)

Tally is a CLI REPL for orchestrating web application penetration testing. It wraps common security tools, stores findings in a RAG knowledge base (ChromaDB + Ollama), and lets you search, chat over, and report on findings — all within a single terminal session.

## Features

- Wraps nmap, Semgrep, OWASP ZAP, OSV-Scanner, pip-audit, npm-audit, composer-audit, and Gitleaks
- Project-based isolation: each project has its own config, vector store, and outputs
- Automatic tool discovery on startup — skips tools that are not installed
- RAG-powered search and chat over ingested findings using Ollama
- Three report formats: Markdown, HTML, JSON
- Human-in-the-loop approval before each tool execution
- Dependency checker validates required packages on every startup
- Docker execution support for all tools

## Requirements

- **Python 3.10+**
- **Ollama** running locally (`ollama serve`) with a chat model and embedding model pulled
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

# 3. Edit global config (set your Ollama models)
cp config/global-example.json config/global.json
# edit config/global.json

# 4. Start Tally — first run launches an interactive tool setup wizard
.venv/bin/python3 tally.py

# 5. Create a project and start scanning
project add
repo add
scan semgrep
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

All scan commands accept `--timeout <seconds>`.

| Command | Description |
|---|---|
| `scan` | Full scan: all segments across all repos |
| `scan -s <segment>` | Segment scan (network, sast, sca, secrets, api) |
| `scan <tool>` | Single tool scan |
| `scan nmap [profile]` | Run nmap (all profiles or one by name) |
| `scan -y` | Auto-approve all tool executions |
| `scan repo` | Language-appropriate tools for an interactively selected repo |
| `scan repo <tool>` | Run a single tool against all repositories |
| `run <tool> [args...]` | Execute a tool with raw arguments |

### Knowledge Base

| Command | Description |
|---|---|
| `search <query>` | Semantic search over ingested findings |
| `chat <message>` | RAG-augmented chat with the LLM |
| `stats` | Show knowledge base statistics |
| `purge --tool <tool>` | Delete all findings from a tool |
| `purge --tool <tool> --profile <profile>` | Delete findings for a specific tool+profile |

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
- [docs/configuration.md](docs/configuration.md) — Config file reference
- [docs/adding-tools.md](docs/adding-tools.md) — Developer guide for adding tool wrappers
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
