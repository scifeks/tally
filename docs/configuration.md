# Tally Configuration Reference

Tally uses JSON files for all configuration. There are two levels: global (application-wide) and project (per-project).

---

## Global Configuration

**File:** `config/global.json`
**Created:** Manually before first run. Copy `config/global-example.json` as a starting point.

This file must exist before Tally starts. If it is missing or invalid, Tally exits with an error.

### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `ollama_base_url` | string | no | `http://localhost:11434` | Ollama API endpoint. Must start with `http://` or `https://`. |
| `default_llm` | string | **yes** | — | Ollama chat model name (e.g. `qwen3:14b`). Must be pulled before use. |
| `default_embedding` | string | **yes** | — | Ollama embedding model name (e.g. `nomic-embed-text:latest`). Must be pulled before use. |
| `projects_dir` | string | no | `./projects` | Directory where project workspaces are stored. |

### Example

```json
{
  "ollama_base_url": "http://localhost:11434",
  "default_llm": "qwen3:14b",
  "default_embedding": "nomic-embed-text:latest",
  "projects_dir": "./projects"
}
```

### Changing the Ollama Endpoint

If Ollama runs on a different host or port, update `ollama_base_url`:

```json
{
  "ollama_base_url": "http://192.168.1.50:11434",
  "default_llm": "qwen3:14b",
  "default_embedding": "nomic-embed-text:latest"
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
| `repositories` | array | no | List of repository objects (mirrors repositories.json). |

#### Example

```json
{
  "project_name": "acme-security-audit",
  "created": "2024-01-14T10:23:45.123456+00:00",
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
| `path` | string | no | Absolute filesystem path to the repository on the host. Required for locally-executed tools. |
| `docker_path` | string | no | Mount path for the repository inside Docker containers. Required when any tool runs in Docker mode. At least one of `path` or `docker_path` must be set. |
| `languages` | array of string | yes | Programming languages in the repo (e.g. `["python", "javascript"]`). Used to select SCA tools. |
| `base_urls` | array of string | no | API base URLs for ZAP scanning (e.g. `["http://localhost:8080"]`). Empty list disables ZAP for this repo. |

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
      "path": "/home/user/projects/acme/api",
      "languages": ["python"],
      "base_urls": ["http://localhost:8080"]
    },
    {
      "name": "frontend",
      "path": "/home/user/projects/acme/frontend",
      "languages": ["javascript", "typescript"],
      "base_urls": []
    }
  ]
}
```

---

### nmap_hosts.json

**File:** `projects/<name>/config/nmap_hosts.json`
**Created:** When `project add` is run. Starts as `{}`.

Defines named nmap scan profiles. Each profile specifies a set of hosts and nmap arguments. Profiles are referenced by name in `scan -t nmap <profile>` and run in sequence during the network segment.

This file must be edited manually — Tally does not provide an interactive interface for nmap profiles.

#### Profile Object Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `hosts` | array of string | yes | List of IP addresses, hostnames, or CIDR ranges to scan. |
| `nmap_args` | string | yes | nmap flags to pass (e.g. `-sV -p 22,80,443`). |

#### Example

```json
{
  "management": {
    "hosts": ["10.0.0.1", "10.0.0.2"],
    "nmap_args": "-sV -p 22,80,443,8080"
  },
  "full-range": {
    "hosts": ["192.168.1.0/24"],
    "nmap_args": "-sV -T4 --top-ports 1000"
  }
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
  "nmap": {
    "type": "repo",
    "location": "local",
    "path": "/usr/bin/nmap"
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
