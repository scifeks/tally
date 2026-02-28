# Web App Pentesting REPL

A CLI-based REPL for orchestrating web application penetration testing tools with RAG-powered analysis.

## Features
- Project-based organization with isolated data stores
- Automated scanning with nmap, Semgrep, OWASP ZAP, OSV-Scanner, Gitleaks
- RAG-powered finding analysis using LlamaIndex + ChromaDB + Ollama
- Human-in-the-loop approval for all tool executions
- Rich CLI interface with progress tracking

## Requirements
- Python 3.10+
- Ollama (for LLM inference)
- System tools: nmap, semgrep, gitleaks, osv-scanner

## Installation
todo

## Usage
todo

## Architecture
```
projects/          # Project-isolated workspaces
  └── [project]/
      ├── config/           # Project configurations
      ├── chroma_db/        # RAG vector store
      ├── tool_outputs/     # Raw scan outputs
      └── sessions/         # Chat history

core/              # Application logic
  ├── config/      # Configuration management
  ├── project/     # Project management
  ├── tools/       # Tool wrappers and execution
  ├── rag/         # RAG engine (LlamaIndex + Chroma)
  └── repl/        # CLI interface

shared/            # Shared knowledge base (OWASP docs, etc.)
```

## License
GNU Affero General Public License v3.0 — see [LICENSE](LICENSE) for details.
