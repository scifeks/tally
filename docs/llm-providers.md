# LLM Provider Configuration

Tally uses LLMs for chat over findings, enrichment during scans, report generation, vector embeddings for RAG search, and AI triage of SAST findings. You configure one or more provider connection profiles in `config/global.json`, then point each feature independently to the provider you want. Multiple providers can coexist in the same configuration.

---

## Providers

### Ollama

**What it is:** Local model serving via a self-hosted Ollama instance. Works for chat, enrichment, embeddings, and triage.

**Setup:**

1. Install Ollama from [ollama.ai](https://ollama.ai).
2. Pull the models you want to use. Example: `ollama pull qwen2.5:14b`.
3. Start the server: `ollama serve`.
4. By default, Ollama listens on `http://localhost:11434`.

**Configuration:**

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:14b",
    "timeout_seconds": 60,
    "num_ctx": null
  }
}
```

**Fields:**

- `base_url`: Server endpoint. Defaults to `http://localhost:11434`. Change this if Ollama runs on a different host or port.
- `model`: Model name (e.g. `qwen2.5:14b`, `mistral:latest`). Must be pulled on the server before use.
- `timeout_seconds`: Request timeout in seconds. Defaults to `60`.
- `num_ctx`: Context window size in tokens. Set to `null` to use the model's default, or specify a number to override.

---

### Anthropic Claude

**What it is:** Cloud-based LLM from Anthropic. Works for chat, enrichment, report generation, and triage.

**Setup:**

1. Create an Anthropic account and get an API key from [console.anthropic.com](https://console.anthropic.com).
2. Set the `ANTHROPIC_API_KEY` environment variable or add `api_key` to the config (recommended: use the env var).
3. No server setup needed; API calls go directly to Anthropic.

**Configuration:**

```json
{
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-6[1m]",
    "max_tokens": 1024,
    "timeout_seconds": 60
  }
}
```

Leave `api_key` empty to use the `ANTHROPIC_API_KEY` environment variable.

**Fields:**

- `api_key`: Anthropic API key. Leave empty to read from `ANTHROPIC_API_KEY` env var (recommended).
- `model`: Anthropic model ID (e.g. `claude-opus-4-6`, `claude-sonnet-5`). Defaults to `claude-opus-4-6[1m]`.
- `max_tokens`: Maximum tokens in the response. Defaults to `1024`.
- `timeout_seconds`: Request timeout in seconds. Defaults to `60`.

---

### OpenAI

**What it is:** Cloud-based LLM from OpenAI. Works for chat, enrichment, and report generation only. Does not provide embeddings; pair with Ollama or Voyage for `embedding_inference`.

**Setup:**

1. Create an OpenAI account and get an API key from [platform.openai.com/account/api-keys](https://platform.openai.com/account/api-keys).
2. Set the `OPENAI_API_KEY` environment variable or add `api_key` to the config (recommended: use the env var).
3. No server setup needed; API calls go directly to OpenAI.

**Configuration:**

```json
{
  "openai": {
    "api_key": "",
    "model": "gpt-4o",
    "max_tokens": 4096,
    "timeout_seconds": 60
  }
}
```

Leave `api_key` empty to use the `OPENAI_API_KEY` environment variable.

**Fields:**

- `api_key`: OpenAI API key. Leave empty to read from `OPENAI_API_KEY` env var (recommended).
- `model`: OpenAI model ID (e.g. `gpt-4o`, `gpt-4o-mini`). Required.
- `max_tokens`: Maximum tokens in the response. Defaults to `4096`.
- `timeout_seconds`: Request timeout in seconds. Defaults to `60`.

---

### llama.cpp

**What it is:** Local model serving via llama.cpp. Works for chat, enrichment, embeddings, and triage.

**Setup:**

1. Build or download llama.cpp from [github.com/ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp).
2. Download a GGUF model file (e.g. from [huggingface.co/models](https://huggingface.co/models)).
3. Start the server: `./llama-server -m <model.gguf>`.
4. By default, llama-server listens on `http://localhost:8000`.

**Configuration:**

```json
{
  "llama_cpp": {
    "base_url": "http://localhost:8080",
    "model": "qwen2.5:14b",
    "timeout_seconds": 60,
    "num_ctx": null
  }
}
```

**Fields:**

- `base_url`: Server endpoint. Defaults to `http://localhost:11434` (shared with Ollama). llama-server typically runs on port 8080; set this to match your server.
- `model`: Model name used in API calls. Must match the model you're serving.
- `timeout_seconds`: Request timeout in seconds. Defaults to `60`.
- `num_ctx`: Context window size in tokens. Set to `null` to use the server's default, or specify a number to override.

---

### Voyage AI

**What it is:** Cloud-based embedding service from Voyage AI. Embedding-only; cannot be used for chat, enrichment, or report inference. Pair with Claude, OpenAI, Ollama, or llama.cpp for LLM features.

**Setup:**

1. Create a Voyage AI account and get an API key from [console.voyageai.com](https://console.voyageai.com).
2. Set the `VOYAGE_API_KEY` environment variable or add `api_key` to the config (recommended: use the env var).
3. No server setup needed; API calls go directly to Voyage.

**Configuration:**

```json
{
  "voyage": {
    "api_key": "",
    "model": "voyage-3",
    "timeout_seconds": 60
  }
}
```

Leave `api_key` empty to use the `VOYAGE_API_KEY` environment variable.

**Fields:**

- `api_key`: Voyage AI API key. Leave empty to read from `VOYAGE_API_KEY` env var (recommended).
- `model`: Voyage embedding model ID (e.g. `voyage-3`, `voyage-3-lite`, `voyage-code-3`). Required.
- `timeout_seconds`: Request timeout in seconds. Defaults to `60`.

---

## Feature Configuration

Each of the five LLM features can use a different provider independently. Configure them by adding a feature inference block to `config/global.json`.

| Feature | Block name | Purpose | Supported providers |
|---------|-----------|---------|-------------------|
| Chat | `chat_inference` | Chat over findings in the REPL and web UI | `ollama`, `llama_cpp`, `claude`, `openai` |
| Enrichment | `enrichment_inference` | Finding enrichment during scan ingest | `ollama`, `llama_cpp`, `claude`, `openai` |
| Reporting | `report_inference` | Report generation via the `report` command | `ollama`, `llama_cpp`, `claude`, `openai` |
| Embeddings | `embedding_inference` | Vector embeddings for RAG retrieval | `ollama`, `llama_cpp`, `voyage` |
| Noir AI | `noir_inference` | AI-assisted endpoint discovery for Noir | `ollama`, `llama_cpp` |
| Triage | `triage_inference` | AI triage of SAST findings in Docker | `ollama`, `llama_cpp`, `claude` |

**Feature configuration fields:**

- `provider` (required): Name of a provider config block (`"ollama"`, `"llama_cpp"`, `"claude"`, `"openai"`, or `"voyage"`).
- `base_url` (optional): Overrides the provider's base URL for this feature only. Must start with `http://` or `https://`.
- `model` (optional): Overrides the provider's model for this feature only. If omitted, uses the provider's model.
- `timeout_seconds` (optional): Overrides the provider's timeout in seconds.
- `num_ctx` (optional): Overrides the context window for local providers (Ollama or llama.cpp).
- `max_tokens` (optional): Overrides max tokens for Claude.
- `retry_count` (optional): Number of retries when the LLM produces unparseable output. Applies to `triage_inference`. Default is 0.
- `debug` (optional): Write raw LLM output to `logs/triage/` for each finding. Applies to `triage_inference`. Default is `false`.

**Example:**

```json
{
  "chat_inference": {
    "provider": "ollama"
  },
  "enrichment_inference": {
    "provider": "ollama"
  },
  "report_inference": {
    "provider": "claude"
  },
  "embedding_inference": {
    "provider": "voyage"
  }
}
```

---

## Common Configurations

### Local Only (Ollama)

All features use a local Ollama instance. No API keys or cloud services needed.

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "qwen2.5:14b",
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
  }
}
```

**Setup:** Pull the models and start Ollama.

```bash
ollama pull qwen2.5:14b
ollama pull nomic-embed-text:latest
ollama serve
```

---

### Claude for Chat and Reports, Local Embeddings

Use Claude's API for chat and reporting (high quality), Ollama locally for embeddings (fast vector search).

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "nomic-embed-text:latest",
    "timeout_seconds": 60
  },
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-6[1m]",
    "max_tokens": 1024,
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "claude"
  },
  "enrichment_inference": {
    "provider": "claude"
  },
  "report_inference": {
    "provider": "claude"
  },
  "embedding_inference": {
    "provider": "ollama"
  }
}
```

**Setup:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
ollama pull nomic-embed-text:latest
ollama serve
```

---

### OpenAI with Local Embeddings

Use OpenAI for chat and enrichment, Ollama locally for embeddings.

```json
{
  "openai": {
    "api_key": "",
    "model": "gpt-4o",
    "max_tokens": 4096,
    "timeout_seconds": 60
  },
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "nomic-embed-text:latest",
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "openai"
  },
  "enrichment_inference": {
    "provider": "openai"
  },
  "report_inference": {
    "provider": "openai"
  },
  "embedding_inference": {
    "provider": "ollama"
  }
}
```

**Setup:**

```bash
export OPENAI_API_KEY="sk-..."
ollama pull nomic-embed-text:latest
ollama serve
```

---

### Claude with Voyage Embeddings

Use Claude for chat, enrichment, and reports; Voyage AI for embeddings (high-quality embeddings, no local overhead).

```json
{
  "claude": {
    "api_key": "",
    "model": "claude-opus-4-6[1m]",
    "max_tokens": 1024,
    "timeout_seconds": 60
  },
  "voyage": {
    "api_key": "",
    "model": "voyage-3",
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "claude"
  },
  "enrichment_inference": {
    "provider": "claude"
  },
  "report_inference": {
    "provider": "claude"
  },
  "embedding_inference": {
    "provider": "voyage"
  }
}
```

**Setup:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export VOYAGE_API_KEY="pa-..."
```

---

## Choosing a Provider

**Local providers (Ollama, llama.cpp)** keep data on your network and require no API keys. Model quality and speed depend on your hardware.

**Cloud providers (Claude, OpenAI)** offer higher quality models without infrastructure. All requests and findings are sent to the provider's servers; check their privacy policies.

**Embedding providers:** Ollama and llama.cpp are local (fast, requires VRAM). Voyage is cloud-based (reliable, no local overhead). OpenAI does not provide embeddings.

**For triage:** Claude Code (API-based) provides the best results. OpenCode (Ollama-based) runs locally but requires Docker and more tuning.

See [docs/configuration.md](configuration.md) for the complete field reference. For triage-specific setup, see [docs/triage.md](triage.md).
