# Tally

[![CI](https://github.com/scifeks/tally/actions/workflows/ci.yml/badge.svg)](https://github.com/scifeks/tally/actions/workflows/ci.yml)

**This tool is for authorized security assessments only. Use Tally only on systems you own or have explicit written permission to test. Unauthorized access to computer systems is illegal.**

Tally is a security auditing platform that eliminates the noise and busy work involved in application security audits. It wraps 20+ security scanners across static analysis, dependency scanning, secrets detection, and web testing. It triages findings with AI, generates reports, and lets you collaborate with an LLM over your findings. Tally is not a replacement for manual auditing and penetration testing, nor does it guarantee finding all vulnerabilities.

## What Tally Does

- Browser-based graphical dashboard for scanning, findings management, triage, reporting, and chat
- Wraps 20+ security scanners across SAST, SCA, DAST, and secrets detection (see [docs/tools.md](docs/tools.md) for the full list)
- AI triage: an LLM agent analyzes each finding with its source code, producing verdict, severity, confidence, remediation, and attack vector
- Claude Code scanning: LLM-driven SAST across Python, PHP, JavaScript, and TypeScript with parallel scanner subagents
- Interactive MCP triage mode: review and confirm triage verdicts in Claude Code before persistence
- Four report formats: Markdown, HTML, JSON, and assembled PDF with LLM-drafted narrative sections
- RAG-powered search and chat over ingested findings
- Project-based isolation: each project has its own configuration, vector store, findings, and reports
- Automatic tool discovery: skips tools that are not installed
- Three interfaces: Web UI (recommended), REPL (terminal), and CLI (non-interactive)
- Project creation from both the web UI and the REPL
- Human-in-the-loop approval before each tool execution
- Docker execution support for all tools
- Header-based authentication for repository access: bearer tokens, API key pairs, and custom HTTP headers with environment variable support (see [docs/configuration.md](docs/configuration.md#authentication-optional))
- Automatic encryption of repository credentials at rest (see [docs/configuration.md](docs/configuration.md#encryption-and-key-management))
- DefectDojo integration for exporting findings to vulnerability management

## Three Interfaces

**Web UI** (recommended). Start with `ui serve` from the REPL. Tally opens a React SPA backed by FastAPI with a graphical interface for scanning, triage, reporting, and chat. See [docs/web-ui.md](docs/web-ui.md) for the full walkthrough.

**REPL**. A terminal interface with interactive commands for scanning, triage, reporting, and configuration. Use the REPL when a web UI is inappropriate: remote servers, SSH sessions, or client-sensitive audits where browser exposure is a concern. See [docs/repl.md](docs/repl.md) for workflows and examples.

**CLI**. A non-interactive entry point for cron jobs, CI pipelines, and scripted automation. See [docs/cli.md](docs/cli.md) for flags and examples.

## Requirements

- **Python 3.10+**
- **Node.js and npm** for the web UI frontend
- **Linux or macOS**
- **An LLM provider**: Tally requires one of the following.
  - Ollama running locally (`ollama serve`) with a chat model and embedding model installed. See [docs/llm-providers.md](docs/llm-providers.md) for setup.
  - Anthropic API key for Claude. Set via the `ANTHROPIC_API_KEY` environment variable or the `claude.api_key` config field.
  - llama.cpp. See [docs/llm-providers.md](docs/llm-providers.md) for setup.
- **Security tools are optional**. Tally skips tools that are not installed. On first run, an interactive setup wizard detects available tools and configures them.

## Quick Start

```bash
# 1. Install Python and Node.js dependencies
bash install.sh

# 2. Configure your LLM provider
cp config/global-example.json config/global.json
# Edit config/global.json to set your LLM provider.
# See docs/llm-providers.md for detailed setup instructions.

# 3. Start Tally (first run launches an interactive tool setup wizard)
.venv/bin/python3 tally.py

# 4. Create a project and add a repository
project add
repo add

# 5. Run your first scan
scan --tool=semgrep

# 6. Launch the web UI
ui serve
```

## REPL Commands

Common commands available in the REPL after starting Tally:

| Command | Description |
|---|---|
| `project add` | Create a new project |
| `project switch <name>` | Switch to a different project |
| `repo add` | Add a repository to scan |
| `repo list` | List configured repositories |
| `scan` | Run a full security scan across all tools |
| `scan --tool=semgrep` | Run a specific tool (Semgrep in this example) |
| `scan --repo=<name>` | Scan a specific repository |
| `burp scan` | Start a Burp crawl-and-audit scan |
| `burp scan <config>` | Start a Burp scan with a named configuration |
| `triage` | Run AI triage on untriaged findings |
| `report` | Generate a security assessment report |
| `chat <question>` | Ask a question about findings |
| `ui serve` | Launch the web UI |

See [docs/repl.md](docs/repl.md) for detailed workflows and additional commands.

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

`config/commands.json` is auto-generated on first run via an interactive setup wizard. Use `tool edit <name>` to change a tool's execution mode at any time. See [docs/docker.md](docs/docker.md) for optional Docker containers for npm-audit and composer-audit.

## Documentation

- [docs/usage.md](docs/usage.md) - Choosing an interface: web UI, REPL, or CLI
- [docs/web-ui.md](docs/web-ui.md) - Web UI walkthrough: dashboard, findings, scans, triage, reports, chat, and configuration
- [docs/repl.md](docs/repl.md) - REPL commands and terminal workflows
- [docs/cli.md](docs/cli.md) - Non-interactive CLI for automation, CI pipelines, and scripted workflows
- [docs/configuration.md](docs/configuration.md) - Config file reference
- [docs/tools.md](docs/tools.md) - Supported tools and detection strategies
- [docs/llm-providers.md](docs/llm-providers.md) - LLM provider setup and configuration for chat, enrichment, reports, embeddings, and triage
- [docs/antares-shim.md](docs/antares-shim.md) - Antares CWE scanner Ollama completions shim configuration
- [docs/chat.md](docs/chat.md) - RAG chat configuration and usage
- [docs/report.md](docs/report.md) - Report generation guide and PDF assembly
- [docs/triage.md](docs/triage.md) - AI triage: auto-triage and MCP triage modes, container lifecycle, and security model
- [docs/claude-code-scanning.md](docs/claude-code-scanning.md) - Claude Code scanning: setup, skills, and MCP server
- [docs/url-discovery.md](docs/url-discovery.md) - URL discovery pipeline for DAST tools
- [docs/endpoint-files.md](docs/endpoint-files.md) - Supplying OAS3, Swagger, Postman, or HAR endpoint files
- [docs/docker.md](docs/docker.md) - Docker containers for npm-audit and composer-audit
- [docs/integrations/defect-dojo.md](docs/integrations/defect-dojo.md) - DefectDojo integration for finding exports
- [docs/adding-tool-wrappers.md](docs/adding-tool-wrappers.md) - Developer guide for adding new tool integrations
- [docs/endpoint-file-adapter-internals.md](docs/endpoint-file-adapter-internals.md) - Developer guide for adding endpoint file format adapters
- [docs/restrictions.md](docs/restrictions.md) - Legal restrictions

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
