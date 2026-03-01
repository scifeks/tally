# Development History: Phases 1–4

## Phase 1: Foundation (TAL-1)

**Commits:** Initial commit → TAL-1 Adding core configuration system → TAL-1 Adding base project management flow

**Deliverables:**
- Directory scaffold: `core/`, `projects/`, `shared/`, `tests/`, `docs/`
- Configuration system with Pydantic validation (`core/config/schemas.py`, `core/config/manager.py`)
  - `GlobalConfig`: required `default_llm`, `default_embedding`; optional `ollama_base_url`, `projects_dir`
  - `ProjectConfig`, `NmapProfile`, `Repository`, `EndpointConfig` schemas
  - `ConfigManager`: strict load — raises `FileNotFoundError` / `ValueError` if config missing or invalid (no silent defaults)
- `ProjectManager` (`core/project/manager.py`): project creation with interview flow, directory scaffolding

**Key files:** `core/config/schemas.py`, `core/config/manager.py`, `core/project/manager.py`

---

## Phase 2: REPL Foundation (TAL-2)

**Commits:** TAL-2 Creating the basic REPL shell → TAL-2 Implementing project management commands

**Deliverables:**
- Rich-based REPL shell (`core/repl/interface.py`) with command dispatch loop
- Entry point: `tally.py`
- Project management commands (`core/repl/commands/project_commands.py`):
  - `new` — guided project creation
  - `open` — load existing project
  - `list` — show all projects
  - `info` — show active project details

**Key files:** `tally.py`, `core/repl/interface.py`, `core/repl/commands/project_commands.py`

---

## Phase 3: Tool Framework + Nmap (TAL-3)

**Commits:**
1. TAL-3 Creating tool wrapper framework
2. TAL-3 Creating tool exec engine
3. TAL-3 Creating nmap wrapper with XML parser and profile-based exec
4. TAL-3 Implementing nmap scan support

**Deliverables:**
- `ToolWrapper` ABC + `ToolResult` dataclass (`core/tools/base.py`)
- `ToolRegistry` singleton with auto-registration (`core/tools/registry.py`)
- `ToolExecutor` with `sanitize_command` for safe shell execution (`core/tools/executor.py`)
- Severity/segment constants (`core/tools/constants.py`)
- `NmapWrapper`: profile-based or ad-hoc host scanning, XML-to-stdout capture (`core/tools/wrappers/nmap.py`)
- `NmapParser`: XML output → structured host/port dicts (`core/tools/parsers/nmap_parser.py`)
- `scan_commands.py`: `scan`, `profiles` REPL commands; human-in-the-loop approval before execution

**Key files:** `core/tools/base.py`, `core/tools/executor.py`, `core/tools/wrappers/nmap.py`, `core/tools/parsers/nmap_parser.py`, `core/repl/commands/scan_commands.py`

---

## Phase 4: RAG Integration (TAL-4)

**Commits:**
1. TAL-4 Creating RAG engine base w/ ChromaDB
2. TAL-4 Creating ingestion pipeline model for RAG
3. TAL-4 Implementing semantic search, chat cmd w/ LLM integration
4. TAL-4 Creating e2e test for nmap+RAG pipeline
5. TAL-4 Raising exception if config missing instead of using default
6. TAL-4 Fixing missing config bug (test fixtures)

**Deliverables:**
- `RAGEngine` (`core/rag/engine.py`): ChromaDB persistent client, project-isolated collection (`findings_<project>`), cosine similarity, Ollama embeddings
- `FindingIngestor` (`core/rag/ingestor.py`): delete-insert upsert; nmap chunks = 1 host doc + N port docs
- `QueryEngine` (`core/rag/query.py`): semantic search + Ollama LLM chat with context injection
- `KnowledgeCommands` (`core/repl/commands/knowledge_commands.py`): `search`, `chat`, `stats` REPL commands
- Live ingestion after scan: `_ingest_result()` in `scan_commands.py`
- End-to-end validation test suite (`tests/validation/test_phase4.py`)

**Key files:** `core/rag/engine.py`, `core/rag/ingestor.py`, `core/rag/query.py`, `core/repl/commands/knowledge_commands.py`

---

## Current State

**Validation:** 29/29 tests pass (`pytest tests/ -v`)

**Working features:**
- Nmap scans (profile-based and ad-hoc)
- Automatic ingestion into ChromaDB after scan
- Semantic search across findings
- LLM-powered chat with RAG context
- Project isolation (separate ChromaDB per project)

**Known constraints:**
- Ollama must be running for ingestion, search, and chat
- `config/global.json` must exist with `default_llm` and `default_embedding` set — app raises `FileNotFoundError` otherwise
- GPU: AMD 7900XTX (24GB VRAM); tested with `qwen3:14b` + `nomic-embed-text:latest` (~9.3GB combined)

---

## Next: Phase 5 — Additional Tools

Planned tool wrappers to add (same pattern as `NmapWrapper`):
- **Semgrep** — static analysis / secret detection
- **OSV-Scanner** — dependency vulnerability scanning
- **Gitleaks** — git history secret scanning
- **OWASP ZAP** — dynamic web app scanning
