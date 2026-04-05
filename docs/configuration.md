# Tally Configuration Reference

Tally uses JSON files for all configuration. There are two levels: global (application-wide) and project (per-project).

---

## Global Configuration

**File:** `config/global.json`
**Created:** Manually before first run. Copy `config/global-example.json` as a starting point.

This file must exist before Tally starts. If it is missing or invalid, Tally exits with an error.

### LLM Provider System

Tally supports multiple LLM backends. Three independent roles determine which provider
handles each type of LLM call:

| Role key | Used by |
|---|---|
| `chat_llm_provider` | The `chat` REPL command |
| `enrichment_llm_provider` | Finding enrichment during ingest |
| `report_llm_provider` | The `report` command |

Each role can be set to `"ollama"` or `"claude"` independently. The corresponding
provider block (`ollama` or `claude`) must be present in `global.json` for any role
that references it.

### Top-level Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `chat_llm_provider` | string | `"ollama"` | Provider for the `chat` command: `"ollama"` or `"claude"`. |
| `enrichment_llm_provider` | string | `"ollama"` | Provider for finding enrichment: `"ollama"` or `"claude"`. |
| `report_llm_provider` | string | `"ollama"` | Provider for report generation: `"ollama"` or `"claude"`. |
| `embedding_provider` | string | `"ollama_embedding"` | Provider for ChromaDB embeddings. Currently only `"ollama_embedding"` is supported. |
| `ollama` | object | — | Ollama connection settings. Required when any LLM role is set to `"ollama"`. |
| `ollama_embedding` | object | — | Ollama embedding settings. Required when `embedding_provider` is `"ollama_embedding"`. |
| `claude` | object | — | Anthropic API settings. Required when any role is set to `"claude"`. |
| `projects_dir` | string | `"./projects"` | Directory where project workspaces are stored. |
| `report_finding_prefix` | string | `"TAL"` | Default prefix for finding IDs in reports (e.g. `TAL-001`). Overridden per-project by `abbreviation`. |
| `location_attestation_confirmed` | bool | `false` | Set to `true` after confirming you are not in a restricted jurisdiction (see Legal Notice). |
| `enrichment_max_concurrency` | int | `4` | Maximum number of concurrent LLM calls during finding enrichment. See [Enrichment Concurrency](#enrichment-concurrency). |

### `ollama` Block Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | string | `"http://localhost:11434"` | Ollama API endpoint. Must start with `http://` or `https://`. |
| `model` | string | — | Chat/enrichment/report model name (e.g. `qwen3:14b`). Must be pulled before use. |
| `timeout_seconds` | int | `60` | Request timeout for all Ollama LLM calls. |

### `ollama_embedding` Block Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | string | `"http://localhost:11434"` | Ollama API endpoint for the embedding service. Must start with `http://` or `https://`. |
| `model` | string | `"nomic-embed-text:latest"` | Embedding model name. Must be pulled before use (`ollama pull nomic-embed-text`). ChromaDB uses this for all vector indexing. |
| `timeout_seconds` | int | `60` | Request timeout for embedding calls. |

### `claude` Block Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | string | `""` | Anthropic API key. Leave empty to use the `ANTHROPIC_API_KEY` environment variable instead (recommended). |
| `model` | string | `"claude-opus-4-5"` | Anthropic model ID (e.g. `claude-opus-4-5`, `claude-haiku-4-5-20251001`). |
| `max_tokens` | int | `1024` | Maximum tokens in the model response. |
| `timeout_seconds` | int | `60` | Request timeout for all Anthropic API calls. |

### Example — Ollama Only

```json
{
  "chat_llm_provider": "ollama",
  "enrichment_llm_provider": "ollama",
  "report_llm_provider": "ollama",
  "embedding_provider": "ollama_embedding",
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "ollama_embedding": {
    "base_url": "http://localhost:11434",
    "model": "nomic-embed-text:latest",
    "timeout_seconds": 60
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

### Example — Claude for Chat and Reporting, Ollama for Enrichment and Embeddings

ChromaDB requires an embedding model. The `ollama_embedding` block is always
required when `embedding_provider` is `"ollama_embedding"`. LLM roles (`chat`,
`enrichment`, `report`) and the embedding provider are configured independently:

```json
{
  "chat_llm_provider": "claude",
  "enrichment_llm_provider": "ollama",
  "report_llm_provider": "claude",
  "embedding_provider": "ollama_embedding",
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "ollama_embedding": {
    "base_url": "http://localhost:11434",
    "model": "nomic-embed-text:latest",
    "timeout_seconds": 60
  },
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-5",
    "max_tokens": 1024,
    "timeout_seconds": 60
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

With `api_key` left empty, Tally reads the key from the `ANTHROPIC_API_KEY`
environment variable at startup.

### Enrichment Concurrency

After a scan completes, Tally enriches each finding by calling the configured LLM
to produce fields such as `severity`, `risk_type`, `remediation`, and `description`.
By default these calls are dispatched concurrently using a thread pool with up to
`enrichment_max_concurrency` (default: `4`) workers.

**Important:** sending concurrent requests only reduces wall-clock time if your
Ollama instance is configured to process them in parallel. Ollama's default is one
request at a time. Set the `OLLAMA_NUM_PARALLEL` environment variable before
starting Ollama to enable parallel slots:

```bash
OLLAMA_NUM_PARALLEL=2 ollama serve
```

`enrichment_max_concurrency` should be set to at least the value of
`OLLAMA_NUM_PARALLEL` so that workers are never idle waiting for a free slot.
Setting it higher than `OLLAMA_NUM_PARALLEL` has no additional benefit.

Keep VRAM headroom in mind when choosing a parallel slot count. Each active slot
holds an independent KV cache for the model. As a rough guide, if your model
occupies X GB at rest, each additional parallel slot adds roughly 10–20% of that
in KV cache overhead at typical enrichment prompt lengths.

### Example — Ollama on a Remote Host

Update `base_url` in both `ollama` and `ollama_embedding` blocks if your
Ollama instance runs on a different host or port:

```json
{
  "chat_llm_provider": "ollama",
  "enrichment_llm_provider": "ollama",
  "report_llm_provider": "ollama",
  "embedding_provider": "ollama_embedding",
  "ollama": {
    "base_url": "http://192.168.1.50:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "ollama_embedding": {
    "base_url": "http://192.168.1.50:11434",
    "model": "nomic-embed-text:latest",
    "timeout_seconds": 60
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

---

## Project Configuration

Each project lives under `projects/<project-name>/`. All project config files are created and managed by Tally. You can edit them manually but Tally will overwrite them on the next write operation.

### project.json

**File:** `projects/<name>/config/project.json`
**Created:** When `new-project` is run.

Stores project metadata. The `repositories` list is kept in sync with `repositories.json` — do not edit it here directly.

#### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `project_name` | string | yes | The project name as entered on creation. |
| `created` | string | yes | ISO 8601 timestamp of when the project was created. |
| `company_name` | string | no | Client company name shown in the report confidentiality blurb. Set during `project add` or `project edit`. |
| `department_name` | string | no | Optional department or team name, stored for reference. |
| `abbreviation` | string | no | Short prefix (max 3 chars) used for finding IDs (e.g. `ACM` → `ACM-001`). Overrides `report_finding_prefix` in `global.json` for this project. |
| `repositories` | array | no | List of repository objects (mirrors repositories.json). |

#### Example

```json
{
  "project_name": "acme-security-audit",
  "created": "2024-01-14T10:23:45.123456+00:00",
  "company_name": "Acme Corp",
  "department_name": "Engineering",
  "abbreviation": "ACM",
  "repositories": []
}
```

---

### repositories.json

**File:** `projects/<name>/config/repositories.json`
**Created:** When the first repository is added via `repo add`.

Stores the list of repositories configured for the project.

#### Repository Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Short identifier used in commands (e.g. `api-server`). |
| `type` | array of string | yes | Repository type(s): `library`, `api`, `ui`. `library` is mutually exclusive with other types. |
| `path` | string | yes | Absolute filesystem path to the repository on the host. Required in all modes — used for language detection and locally-executed tools. |
| `docker_path` | string | no | Mount path for the repository inside Docker containers. Set when any tool runs in Docker mode. |
| `container_name` | string | yes (Docker) | Name of the running Docker container (as shown by `docker ps`). Required when `docker_path` is set. |
| `languages` | array of string | yes | Programming languages in the repo (e.g. `["python", "javascript"]`). Used to select SCA tools. |
| `base_urls` | array of string | no | API base URLs for ZAP scanning (e.g. `["http://localhost:8080"]`). Empty list disables ZAP for this repo. |
| `test_dirs` | array of string | no | Directory names treated as test directories (matched by name at any depth, case-insensitive). Findings in these directories are excluded from SAST and secrets results. |
| `ignore_dirs` | array of string | no | Directory names to exclude from SAST and secrets scans (matched by name at any depth, case-insensitive). |
| `dependencies_file` | string | no | Path to a Python dependencies file for pip-audit. See [pip-audit dependency file](tools.md#pip-audit-dependency-file) for details. |

Supported language values for SCA tool selection:
- `python` → pip-audit
- `javascript`, `typescript`, `node` → npm-audit
- `php` → composer-audit

#### Example

```json
{
  "repositories": [
    {
      "name": "api-server",
      "type": ["api"],
      "path": "/home/user/projects/acme/api",
      "languages": ["python"],
      "base_urls": ["http://localhost:8080"],
      "dependencies_file": "requirements.txt"
    },
    {
      "name": "frontend",
      "type": ["ui"],
      "path": "/home/user/projects/acme/frontend",
      "languages": ["javascript", "typescript"],
      "base_urls": []
    }
  ]
}
```

---

### endpoints/\<repo\>.json

**File:** `projects/<name>/config/endpoints/<repo-name>.json`
**Created:** Manually or by future tooling. Optional.

Configures API endpoint details for ZAP scanning of a specific repository. If this file does not exist, ZAP uses only the `base_url` from `repositories.json`.

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `format_version` | string | no | `"1.0"` | Config format version. |
| `repo_name` | string | yes | — | Must match the repository name in `repositories.json`. |
| `api_type` | string | no | `"rest"` | API type: `rest` or `graphql`. |
| `endpoints` | object | no | `{}` | HTTP methods mapped to lists of endpoint paths. |

#### Example

```json
{
  "format_version": "1.0",
  "repo_name": "api-server",
  "api_type": "rest",
  "endpoints": {
    "GET": ["/api/users", "/api/users/{id}", "/api/health"],
    "POST": ["/api/users", "/api/auth/login"],
    "DELETE": ["/api/users/{id}"]
  }
}
```

---

### commands.json (project-level overrides)

**File:** `projects/<name>/config/commands.json`
**Created:** When `tool add --project=<name>` is first run for the project.

Each entry in this file fully replaces the global `config/commands.json` entry for
the same tool name when scans run against this project. Tools not listed here
continue to use the global configuration.

The structure mirrors global `config/commands.json` exactly. See the
[Tool Configuration](#tool-configuration) section below for field definitions.

#### Example

```json
{
  "semgrep": {
    "type": "repo",
    "location": "docker",
    "container": {
      "name": "semgrep-project-container",
      "tool_path": "/usr/local/bin/semgrep"
    }
  }
}
```

In this example, when a scan runs against the project, semgrep uses a
project-specific Docker container instead of the globally configured one.
All other tools use the global config.

---

## Tool Configuration

**File:** `config/commands.json`
**Created:** Automatically on first run via an interactive setup wizard. Can be re-generated by deleting the file and restarting Tally.

This file is the tool registry. It records which tools are configured and how each one is executed. Entries are managed via `tool add`, `tool edit`, and `tool remove` in the REPL; you can also edit the file directly.

If `config/commands.json` does not exist when Tally starts, it launches an interactive setup wizard that detects installed tools and writes the file.

### Fields

Each top-level key is a tool name (e.g. `semgrep`). The value is a `CommandEntry` object:

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | `"repo"` for repository-scoped tools; `"api"` for API/network tools (e.g. ZAP). |
| `location` | string | yes | `"local"` to run the tool as a subprocess; `"docker"` to run via `docker exec`. |
| `path` | string | yes (local) | Absolute path to the tool binary on the host. Required when `location` is `"local"`. |
| `container` | object | yes (docker) | Docker container configuration. Required when `location` is `"docker"`. |

The `container` object has two fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Name of the running Docker container (as shown by `docker ps`). |
| `tool_path` | string | yes | Absolute path to the tool binary inside the container. |

### Example — Local Tool

```json
{
  "semgrep": {
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/semgrep"
  }
}
```

### Example — Docker Tool

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

### Full Example

```json
{
  "gitleaks": {
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/gitleaks"
  },
  "semgrep": {
    "type": "repo",
    "location": "docker",
    "container": {
      "name": "semgrep-container",
      "tool_path": "/usr/local/bin/semgrep"
    }
  },
  "zap": {
    "type": "api",
    "location": "local",
    "path": "/usr/bin/zaproxy"
  }
}
```

---

## Startup Flags

These flags are passed directly to `tally.py` and are not stored in any config file.

| Flag | Description |
|---|---|
| `--check` | Run dependency check, print results, and exit. Returns exit code 0 if all required dependencies are present, 1 if any are missing. Does not start the REPL. |
| `--skip-checks` | Skip the dependency check entirely. Useful during development when you know the environment is configured. |

Examples:

```bash
# Verify your environment without starting Tally
.venv/bin/python3 tally.py --check

# Start without the dependency check delay
.venv/bin/python3 tally.py --skip-checks
```
