# Tally

Tally is a CLI REPL for orchestrating web application penetration testing. It wraps common security tools, stores findings in a RAG knowledge base (ChromaDB + Ollama), and lets you search, chat over, and report on findings — all within a single terminal session.

## Features

- Wraps nmap, Semgrep, OWASP ZAP, OSV-Scanner, pip-audit, npm-audit, composer-audit, and Gitleaks
- Project-based isolation: each project has its own config, vector store, and outputs
- Automatic tool discovery on startup — skips tools that are not installed
- RAG-powered search and chat over ingested findings using Ollama
- Three report formats: Markdown, HTML, JSON
- Human-in-the-loop approval before each tool execution
- Dependency checker validates required packages on every startup

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

# 4. Start Tally
.venv/bin/python3 tally.py

# 5. Create a project and start scanning
new-project
add-repo
scan -t semgrep
report
```

## REPL Command Reference

### Project Management

| Command | Description |
|---|---|
| `new-project` | Create a new project (interactive) |
| `projects` | List all projects |
| `switch <name>` | Switch active project |
| `project-info` | Show active project details |
| `add-repo` | Add a repository to the active project |
| `repos` | List configured repositories |
| `edit-repo <name>` | Edit a repository's config |
| `delete-repo <name>` | Delete a repository's config |

### Scanning

All scan commands accept `--timeout <seconds>`.

| Command | Description |
|---|---|
| `scan` | Full scan: all segments across all repos |
| `scan -s <segment>` | Segment scan (network, sast, sca, secrets, api) |
| `scan -t <tool>` | Single tool scan |
| `scan -t nmap [profile]` | Run nmap (all profiles or one by name) |
| `scan -y` | Auto-approve all tool executions |
| `repo-scan [<repo>]` | Language-appropriate tools for a single repo |
| `repo-scan --severity <level>` | Filter by severity (critical/high/medium/low) |
| `repo-scan --exclude <dirs>` | Exclude directories (comma-separated) |
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

## Startup Flags

```bash
.venv/bin/python3 tally.py --check        # Check dependencies and exit
.venv/bin/python3 tally.py --skip-checks  # Skip dependency check (development)
```

## Documentation

- [docs/usage.md](docs/usage.md) — Full usage guide with examples
- [docs/configuration.md](docs/configuration.md) — Config file reference
- [docs/adding-tools.md](docs/adding-tools.md) — Developer guide for adding tool wrappers

## License

GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.
