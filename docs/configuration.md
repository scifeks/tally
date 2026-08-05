# Tally Configuration Reference

Tally uses JSON files for all configuration. There are two levels: global (application-wide) and project (per-project).

---

## Global Configuration

**File:** `config/global.json`
**Created:** Manually before first run. Copy `config/global-example.json` as a starting point.

This file must exist before Tally starts. If it is missing or invalid, Tally exits with an error.

### LLM Provider System

Tally uses a two-layer provider configuration system. Provider configs define connection profiles for Ollama, Llama.cpp, or Claude. Feature configs reference a provider and optionally override settings per feature.

Each of five inference features can use a different provider independently:

| Feature config | Used by |
|---|---|
| `chat_inference` | Chat over findings in the REPL and web UI |
| `enrichment_inference` | Finding enrichment during ingest |
| `report_inference` | The `report` command |
| `embedding_inference` | ChromaDB vector embeddings |
| `noir_inference` | NOIR security API |

Triage uses the same feature-inference pattern through `triage_inference`. The `provider` field selects which provider block supplies the base URL and default model. Optional overrides like `model` work the same way as for other features.

### Top-level Fields

| Field | Type | Description |
|---|---|---|
| `ollama` | object | Ollama provider config. Connection profile for local or remote Ollama instances. See [Provider Config Fields](#provider-config-fields). |
| `llama_cpp` | object | Llama.cpp provider config. Connection profile for Llama.cpp servers. See [Provider Config Fields](#provider-config-fields). |
| `claude` | object | Claude provider config. Anthropic API settings. Required when any feature references `"claude"`. See [Claude Provider Fields](#claude-provider-fields). |
| `openai` | object | OpenAI provider config. Required when any feature references `"openai"`. See [OpenAI Provider Fields](#openai-provider-fields). |
| `voyage` | object | Voyage AI embedding provider config. Required when `embedding_inference` references `"voyage"`. See [Voyage Provider Fields](#voyage-provider-fields). |
| `chat_inference` | object | Chat over findings in the REPL and web UI. See [Feature Config Fields](#feature-config-fields). |
| `enrichment_inference` | object | Feature config for finding enrichment during ingest. See [Feature Config Fields](#feature-config-fields). |
| `report_inference` | object | Feature config for the `report` command. See [Feature Config Fields](#feature-config-fields). |
| `embedding_inference` | object | Feature config for ChromaDB vector embeddings. See [Feature Config Fields](#feature-config-fields). |
| `noir_inference` | object | Feature config for NOIR security API. See [Feature Config Fields](#feature-config-fields). |
| `triage_inference` | object | Feature config for AI triage. Requires Docker. See [Feature Config Fields](#feature-config-fields) and [docs/triage.md](triage.md). |
| `antares_inference` | object | Feature config for Antares CWE scanner LLM backend. See [Feature Config Fields](#feature-config-fields) and [docs/antares-shim.md](antares-shim.md). |
| `defectdojo` | object | DefectDojo connection settings. See [DefectDojo Fields](#defectdojo-fields) and [docs/integrations/defect-dojo.md](integrations/defect-dojo.md). |
| `post_scan_sync` | list\[string\] | Integrations to auto-sync after each scan. Supported values: `"defectdojo"`. Default: `[]` (disabled). See [docs/integrations/defect-dojo.md](integrations/defect-dojo.md#automatic-post-scan-sync). |
| `post_triage_sync` | list\[string\] | Integrations to auto-sync after triage. Supported values: `"defectdojo"`. Default: `[]` (disabled). See [docs/integrations/defect-dojo.md](integrations/defect-dojo.md#automatic-post-triage-sync). |
| `projects_dir` | string | Directory where project workspaces are stored. Default: `"./projects"`. |
| `report_finding_prefix` | string | Default prefix for finding IDs in reports (e.g. `TAL-001`). Overridden per-project by `abbreviation`. Default: `"TAL"`. |
| `location_attestation_confirmed` | bool | Set to `true` after confirming you are not in a restricted jurisdiction (see Legal Notice). Default: `false`. |
| `enrichment_max_concurrency` | int | Maximum number of concurrent LLM calls during finding enrichment. See [Enrichment Concurrency](#enrichment-concurrency). Default: `4`. |
| `web_ui_host` | string | `"127.0.0.1"` | Bind address for the FastAPI server and Vite dev server. `0.0.0.0` and `::` are rejected. Use an explicit loopback or LAN IP. |
| `web_ui_port` | int | `8080` | TCP port for the FastAPI server started by `ui serve`. |
| `web_ui_vite_port` | int | `3000` | TCP port for the Vite dev server started by `ui serve`. |
| `web_ui_allowed_origins` | list\[string\] | derived | CORS allow-list for the Vite dev server. Defaults to `["https://<web_ui_host>:<web_ui_vite_port>"]` when absent or empty. Override only when running Vite under a different hostname. |
| `mcp_port` | int | `8765` | TCP port for the MCP triage server started by `tally mcp serve`. |

### TLS Certificate Configuration

The web UI runs over HTTPS using a self-signed TLS certificate. The certificate is generated automatically during `install.sh` for the default host (`127.0.0.1`).

**Certificate files:**

- `config/tls/cert.pem` - Self-signed certificate
- `config/tls/key.pem` - Private key

Your browser will show a security warning for self-signed certificates. Accept the warning to proceed (the certificate is only trusted for your local machine).

**Regenerating the certificate**

If you change `web_ui_host` to a different address, regenerate the TLS certificate from the REPL:

```
[project]> ui ssl regenerate
```

This creates a new self-signed certificate for the updated `web_ui_host`. Regeneration is required for the browser to recognize the new hostname.

---

### Provider Config Fields

The `ollama` and `llama_cpp` provider configs share the same schema:

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | string | `"http://localhost:11434"` (ollama only) | Server endpoint. Must start with `http://` or `https://`. |
| `model` | string | (required) | Model name (e.g. `qwen3:14b`). Required. Must be available on the server before use. |
| `timeout_seconds` | int | `60` | Request timeout in seconds for LLM calls. |
| `num_ctx` | int or null | `null` | Context window size. Pass `null` to use the model's default. |

### Claude Provider Fields

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | string | `""` | Anthropic API key. Leave empty to use the `ANTHROPIC_API_KEY` environment variable instead (recommended). Also used for triage when `triage_inference.provider` is `"claude"`. |
| `model` | string | `"claude-opus-4-5"` | Anthropic model ID (e.g. `claude-opus-4-5`, `claude-haiku-4-5-20251001`). Also controls the triage model when using the Claude Code backend. |
| `max_tokens` | int | `1024` | Maximum tokens in the model response. |
| `timeout_seconds` | int | `60` | Request timeout in seconds for Anthropic API calls. |

### OpenAI Provider Fields

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | string | `""` | OpenAI API key. Leave empty to use the `OPENAI_API_KEY` environment variable instead (recommended). |
| `model` | string | (required) | OpenAI model ID (e.g. `gpt-4o`, `gpt-4o-mini`). |
| `max_tokens` | int | `4096` | Maximum tokens in the model response. |
| `timeout_seconds` | int | `60` | Request timeout in seconds for OpenAI API calls. |

### Voyage Provider Fields

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | string | `""` | Voyage AI API key. Leave empty to use the `VOYAGE_API_KEY` environment variable instead (recommended). |
| `model` | string | (required) | Voyage embedding model ID (e.g. `voyage-3`, `voyage-3-lite`, `voyage-code-3`). |
| `timeout_seconds` | int | `60` | Request timeout in seconds for Voyage API calls. |

### Feature Config Fields

Each of the five inference features (`chat_inference`, `enrichment_inference`,
`report_inference`, `embedding_inference`, `noir_inference`) uses the same
feature config schema:

#### Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | string | (required) | Name of a provider config block: `"ollama"`, `"llama_cpp"`, `"claude"`, `"openai"`, or `"voyage"`. Required. |
| `model` | string or null | `null` | Overrides the provider's model for this feature only. If `null`, uses the provider's model. |
| `timeout_seconds` | int or null | `null` | Overrides the provider's timeout in seconds. Must be positive if set. If `null`, uses the provider's timeout. |
| `num_ctx` | int or null | `null` | Overrides the provider's context window (local providers only). Must be positive if set. If `null`, uses the provider's value. |
| `max_tokens` | int or null | `null` | Overrides the provider's max tokens (Claude only). Must be positive if set. If `null`, uses the provider's value. |
| `retry_count` | int or null | `null` | Number of per-finding retries when the triage agent produces unparseable output. Applies to `triage_inference` only. Default is 0 (no retry). |
| `debug` | bool | `false` | Write raw agent output to `logs/triage/` for each finding. Applies to `triage_inference` only. |

### `opencode` Block Fields

| Field | Type | Default | Description |
|---|---|---|---|
| `api_key` | string | `""` | API key passed to the OpenCode agent. Set to any non-empty value when running against Ollama (e.g. `"ollama"`). |
| `api_provider` | string | `""` | LLM endpoint URL (e.g. `http://localhost:11434`). Used for network egress allowlisting in the triage container. |

### DefectDojo Fields

Optional. Required only when using the `sync --integration=defectdojo` command.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `url` | string | Yes | | Base URL of your DefectDojo instance. Must use `http://` or `https://`. |
| `api_token` | string | Yes | | API v2 token from your DefectDojo user profile. |
| `verify_ssl` | bool | No | `true` | Verify TLS certificates. Set to `false` for self-signed certificates. |
| `product_type` | string | No | `"Tally Scan"` | Product Type label in DefectDojo. Groups all repo Products under a common type. |
| `engagement_type` | string | No | `"Tally Engagement"` | Default Engagement name. Can be overridden per project or per invocation. |
| `auto_create_context` | bool | No | `true` | Create Product, Engagement, and Product Type in DefectDojo if they do not exist. |
| `scan_type` | string | No | `"Generic Findings Import"` | DefectDojo scan type used for the import. Controls the "Found By" label. |

See [docs/integrations/defect-dojo.md](integrations/defect-dojo.md) for entity mapping, engagement type cascade, and usage.

### Example: Ollama Only

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "ollama"
  },
  "enrichment_inference": {
    "provider": "ollama"
  },
  "report_inference": {
    "provider": "ollama"
  },
  "embedding_inference": {
    "provider": "ollama",
    "model": "nomic-embed-text:latest"
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

### Example: Claude for Chat and Reporting, Ollama for Enrichment and Embeddings

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-5",
    "max_tokens": 1024,
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "claude"
  },
  "enrichment_inference": {
    "provider": "ollama"
  },
  "report_inference": {
    "provider": "claude"
  },
  "embedding_inference": {
    "provider": "ollama",
    "model": "nomic-embed-text:latest"
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

Leave `api_key` empty to have Tally read the key from the `ANTHROPIC_API_KEY` environment variable at startup.

### Example: Enable Claude Code Triage

Triage runs inside a Docker container. Docker must be installed and running.
Add a `triage_inference` block referencing the `claude` provider.
See [docs/triage.md](triage.md) for setup details and the full security model.

```json
{
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-5",
    "max_tokens": 1024,
    "timeout_seconds": 60
  },
  "triage_inference": {
    "provider": "claude"
  }
}
```

Leave `api_key` empty for Tally to use the `ANTHROPIC_API_KEY` environment variable for LLM API calls and fall back to OAuth file mounts for triage container authentication.

### Example: Enable Local Model Triage

Triage runs inside a Docker container. Docker must be installed and running.
Add a `triage_inference` block referencing the provider and optionally
override the model. See [docs/triage.md](triage.md) for setup details.

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:14b"
  },
  "triage_inference": {
    "provider": "ollama",
    "model": "qwen3-coder:30b"
  }
}
```

### Enrichment Concurrency

After a scan completes, Tally enriches each finding by calling the configured LLM to produce fields like `severity`, `risk_type`, `remediation`, and `description`. By default, these calls are dispatched concurrently using a thread pool with up to `enrichment_max_concurrency` (default: `4`) workers.

When using the `ollama` provider for enrichment, sending concurrent requests only reduces wall-clock time if your Ollama instance is configured to process them in parallel. Ollama's default is one request at a time. Set the `OLLAMA_NUM_PARALLEL` environment variable before starting Ollama to enable parallel slots:

```bash
OLLAMA_NUM_PARALLEL=2 ollama serve
```

`enrichment_max_concurrency` should be set to at least the value of
`OLLAMA_NUM_PARALLEL` so that workers are never idle waiting for a free slot.
Setting it higher than `OLLAMA_NUM_PARALLEL` has no additional benefit.

Keep VRAM headroom in mind when choosing a parallel slot count. Each active slot holds an independent KV cache for the model. As a rough guide, if your model occupies X GB at rest, each additional parallel slot adds roughly 10-20% of that in KV cache overhead at typical enrichment prompt lengths.

### Example: Ollama on a Remote Host

Update `base_url` in the `ollama` provider block if your Ollama instance runs
on a different host or port:

```json
{
  "ollama": {
    "base_url": "http://192.168.1.50:11434",
    "model": "qwen3:14b",
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "ollama"
  },
  "enrichment_inference": {
    "provider": "ollama"
  },
  "report_inference": {
    "provider": "ollama"
  },
  "embedding_inference": {
    "provider": "ollama",
    "model": "nomic-embed-text:latest"
  },
  "projects_dir": "./projects",
  "report_finding_prefix": "TAL",
  "location_attestation_confirmed": false
}
```

---

## Project Configuration

Each project lives under `projects/<project-name>/`. All project config files are created and managed by Tally. You can edit them manually, but Tally will overwrite them on the next write operation.

### project.json

**File:** `projects/<name>/config/project.json`
**Created:** When `project add` is run.

Stores project metadata. The `repositories` list is kept in sync with `repositories.json`. Do not edit the list directly in this file.

#### Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `project_name` | string | yes | The project name as entered on creation. |
| `created` | string | yes | ISO 8601 timestamp of when the project was created. |
| `company_name` | string | no | Client company name shown in the report confidentiality blurb. Set during `project add` or `project edit`. |
| `department_name` | string | no | Optional department or team name, stored for reference. |
| `abbreviation` | string | no | Short prefix (max 3 chars) used for finding IDs (e.g. `ACM` → `ACM-001`). Overrides `report_finding_prefix` in `global.json` for this project. |
| `defectdojo` | object | no | Optional DefectDojo overrides for this project. See [DefectDojo Project Fields](#defectdojo-project-fields). |
| `repositories` | array | no | List of repository objects (mirrors repositories.json). |

#### DefectDojo Project Fields

Optional. Overrides global DefectDojo defaults for this project.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `engagement_type` | string | No | | Overrides the global `engagement_type` for this project. |

See [docs/integrations/defect-dojo.md](integrations/defect-dojo.md) for the engagement type cascade and entity mapping.

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
| `path` | string | yes | Absolute filesystem path to the repository on the host. Required in all modes; used for language detection and locally-executed tools. |
| `docker_path` | string | no | Mount path for the repository inside Docker containers. Set when any tool runs in Docker mode. |
| `container_name` | string | yes (Docker) | Name of the running Docker container (as shown by `docker ps`). Required when `docker_path` is set. |
| `languages` | array of string | yes | Programming languages in the repo (e.g. `["python", "javascript"]`). Used to select SCA tools. |
| `base_urls` | array of string | no | API base URLs for ZAP scanning (e.g. `["http://localhost:8080"]`). Empty list disables ZAP for this repo. |
| `test_dirs` | array of string | no | Directory names treated as test directories (matched by name at any depth, case-insensitive). Findings in these directories are excluded from SAST and secrets results. |
| `ignore_dirs` | array of string | no | Directory names to exclude from SAST and secrets scans (matched by name at any depth, case-insensitive). |
| `dependencies_file` | string | no | Path to a Python dependencies file for pip-audit. See [pip-audit dependency file](tools.md#pip-audit-dependency-file) for details. |
| `auth` | object | no | Optional authentication configuration for this repository. Supports form-based login or header-based injection. See [Authentication (Optional)](#authentication-optional) for details. |

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

### Authentication (Optional)

When present, the `auth` field configures how Tally authenticates with the target repository or application. Two strategies are supported.

#### Form-based Login

For applications with HTML login forms, set `auth_type` to `"form"`. Tally performs a pre-scan login by POSTing to `login_url`, extracts the session cookie, and injects it into crawlers (Katana) and dynamic analysis tools (sqlmap, DalFox, XSStrike, graphql-cop).

##### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `auth_type` | string | yes | `"form"` | Set to `"form"` for form-based login. |
| `login_url` | string | yes | | Full URL of the login form endpoint (e.g. `http://localhost:8080/auth/login`). |
| `username_field` | string | no | `"username"` | HTML input name attribute for the username field. |
| `password_field` | string | no | `"password"` | HTML input name attribute for the password field. |
| `extra_fields` | object | no | `{}` | Additional form fields as key-value pairs (e.g. `{"submit": "Login", "remember": "on"}`). |
| `credentials_env` | string | no | | Environment variable containing credentials in `user:pass` format. Takes precedence over inline `username` and `password` when set. |
| `username` | string | no | | Inline username. Used only if `credentials_env` is not set. |
| `password` | string | no | | Inline password. Used only if `credentials_env` is not set. |
| `verify_ssl` | bool | no | `true` | Verify TLS certificates. Set to `false` for self-signed certificates on local dev stacks. |

#### Header-based Auth

For APIs and applications using bearer tokens, API keys, or other header-based authentication, set `auth_type` to `"header"`. Tally injects configured headers into all tool requests (Katana, sqlmap, DalFox, XSStrike, graphql-cop).

##### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `auth_type` | string | yes | | Set to `"header"` for header-based auth. |
| `auth_headers` | array of object | yes | | List of header entries to inject. See [Auth Headers](#auth-headers) below. |

#### Auth Headers

Each entry in `auth_headers` represents a single HTTP header.

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `header` | string | yes | | HTTP header name (e.g. `"Authorization"`, `"X-API-Key"`). |
| `value` | string | no | | Inline header value. Encrypted at rest. Leave empty if using `value_env` instead. |
| `value_env` | string | no | | Environment variable containing the header value. Takes precedence over `value` when set. |

#### Example: Form-based Login with Inline Credentials

```json
{
  "repositories": [
    {
      "name": "target-app",
      "type": ["api"],
      "path": "/path/to/repo",
      "languages": ["javascript"],
      "base_urls": ["http://localhost:8080"],
      "auth": {
        "auth_type": "form",
        "login_url": "http://localhost:8080/auth/login",
        "username_field": "email",
        "password_field": "password",
        "username": "testuser",
        "password": "testpass"
      }
    }
  ]
}
```

#### Example: Form-based Login with Environment Variables

```json
{
  "repositories": [
    {
      "name": "target-app",
      "type": ["api"],
      "path": "/path/to/repo",
      "languages": ["javascript"],
      "base_urls": ["http://localhost:8080"],
      "auth": {
        "auth_type": "form",
        "login_url": "http://localhost:8080/auth/login",
        "username_field": "email",
        "password_field": "password",
        "credentials_env": "APP_CREDENTIALS"
      }
    }
  ]
}
```

Set the environment variable before running Tally: `APP_CREDENTIALS=testuser:testpass`.

#### Example: Bearer Token

```json
{
  "repositories": [
    {
      "name": "api-service",
      "type": ["api"],
      "path": "/path/to/repo",
      "languages": ["python"],
      "base_urls": ["http://localhost:5000"],
      "auth": {
        "auth_type": "header",
        "auth_headers": [
          {
            "header": "Authorization",
            "value": "Bearer your-token-here"
          }
        ]
      }
    }
  ]
}
```

#### Example: API Key Pair

```json
{
  "repositories": [
    {
      "name": "api-service",
      "type": ["api"],
      "path": "/path/to/repo",
      "languages": ["python"],
      "base_urls": ["http://localhost:5000"],
      "auth": {
        "auth_type": "header",
        "auth_headers": [
          {
            "header": "X-API-Key",
            "value": "api-key-id"
          },
          {
            "header": "X-API-Secret",
            "value": "api-secret-value"
          }
        ]
      }
    }
  ]
}
```

#### Example: Headers with Environment Variables (Recommended)

```json
{
  "repositories": [
    {
      "name": "api-service",
      "type": ["api"],
      "path": "/path/to/repo",
      "languages": ["python"],
      "base_urls": ["http://localhost:5000"],
      "auth": {
        "auth_type": "header",
        "auth_headers": [
          {
            "header": "Authorization",
            "value_env": "API_TOKEN"
          }
        ]
      }
    }
  ]
}
```

Set the environment variable before running Tally: `API_TOKEN=Bearer your-token-here`.

### Encryption and Key Management

When you create a project with `project add`, Tally prompts you to set an encryption passphrase. This passphrase is used to derive a Fernet encryption key that encrypts all stored credentials (form passwords, API keys, bearer tokens).

#### Key Creation

During project creation, Tally derives a key from your passphrase using PBKDF2-HMAC-SHA256 with 600,000 iterations and 16 random salt bytes. The derived key and salt are stored in a key file (default location: `projects/<project-name>/config/.tally_encryption_key`).

Key file permissions are set to `0600` (owner read/write only) to prevent unauthorized access.

#### Key File Location

By default, the key file is stored alongside the project's SQLite database. During project creation, you can choose a custom location (recommended: outside the project directory to prevent accidental commits).

#### Overriding the Key with an Environment Variable

For CI/CD pipelines, headless deployments, or when the key file is inaccessible, set the `TALLY_ENCRYPTION_KEY` environment variable. The variable value should be a Fernet key (base64-encoded string). When set, this overrides the key file:

```bash
export TALLY_ENCRYPTION_KEY="your-fernet-key-here"
tally
```

If `TALLY_ENCRYPTION_KEY` is not set, Tally reads the key from the key file.

#### Managing Keys with REPL Commands

Use the `project key` command to check encryption status, set up encryption for existing projects, or rotate keys:

| Command | Description |
|---|---|
| `project key status` | Show encryption status and key file location (resolves symlinks) |
| `project key setup` | Add encryption to an existing unencrypted project. Prompts for passphrase and key file location. Re-encrypts any existing unencrypted auth data. |
| `project key change` | Rotate the encryption key. Decrypts all auth data with the old key, prompts for new passphrase, optionally moves the key file to a new location (with symlink), and re-encrypts all auth data with the new key. |

---

### endpoints/\<repo\>.json

**File:** `projects/<name>/config/endpoints/<repo-name>.json`
**Created:** Manually or by future tooling. Optional.

Configures API endpoint details for ZAP scanning of a specific repository. If this file does not exist, ZAP uses only the `base_url` from `repositories.json`.

#### Fields

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `format_version` | string | no | `"1.0"` | Config format version. |
| `repo_name` | string | yes | (required) | Must match the repository name in `repositories.json`. |
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

### Example: Local Tool

```json
{
  "semgrep": {
    "type": "repo",
    "location": "local",
    "path": "/usr/local/bin/semgrep"
  }
}
```

### Example: Docker Tool

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
