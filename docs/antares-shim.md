# Antares CWE Scanner and Ollama Completions Shim

Antares is a SAST scanner that uses a small language model to investigate your codebase and identify files likely to contain specific CWE weaknesses. Unlike pattern-based scanners, Antares explores source code paths, data flows, and vulnerability patterns to localize where weaknesses are most likely to exist.

---

## What the Completions Shim Does

Antares is built on IBM's Granite model and expects a raw text completions endpoint (OpenAI-style `/v1/completions`). It builds its own chat template and does not use the chat-completion API. When you configure Tally to use Ollama as the Antares backend, Tally runs a local HTTP shim that translates between two APIs:

- **Incoming:** OpenAI-format `/v1/completions` requests from Antares
- **Outgoing:** Ollama-format `/api/generate` calls to your running Ollama instance

The shim sets `raw=True` in the Ollama request, which tells Ollama to skip its own template and run the prompt as-is. This allows Antares to format the prompt using Granite's native template.

---

## Supported Backends

You can configure Antares to use any of three LLM backends via `antares_inference.provider` in `config/global.json`:

### Ollama (with automatic shim)

**Provider value:** `"ollama"`

Requires Ollama to be running locally. Tally automatically starts the completions shim, which listens on a local port and translates requests. This is the recommended option when Ollama is available.

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "granite3-dense:2b"
  },
  "antares_inference": {
    "provider": "ollama",
    "model": "granite3-dense:2b"
  }
}
```

### Llama-server (llama.cpp)

**Provider value:** `"llama_cpp"`

Use llama-server (from [llama.cpp](https://github.com/ggerganov/llama.cpp)) if you prefer running models via llama.cpp. Specify `base_url` in the `antares_inference` block or the `llama_cpp` provider config.

```json
{
  "antares_inference": {
    "provider": "llama_cpp",
    "base_url": "http://localhost:8000"
  }
}
```

Llama-server already exposes `/v1/completions`, so no shim is needed.

### vLLM

**Provider value:** `"vllm"`

Use vLLM for high-throughput serving. Specify `base_url` in the `antares_inference` block.

```json
{
  "antares_inference": {
    "provider": "vllm",
    "base_url": "http://192.168.1.50:8000"
  }
}
```

vLLM already exposes `/v1/completions`, so no shim is needed.

---

## Configuration

Add an `antares_inference` block to your global config (`config/global.json`):

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | string | Yes | - | LLM backend: `"ollama"`, `"llama_cpp"`, or `"vllm"` |
| `model` | string | No | Fallback chain (see below) | Model name for Antares. If omitted, resolves from chat/triage Ollama models or provider config |
| `base_url` | string | No | From provider config | Override endpoint URL. Required for `llama_cpp` and `vllm` if not set in their provider blocks |
| `timeout_seconds` | int | No | `300` | Timeout in seconds for completions requests. Accounts for cold-start after model load |

Optionally add an `antares_sweep_config` block for CWE sweep parameters:

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `max_cwes` | int | No | Unset | Maximum CWE vulnerability classes to scan per sweep. Lower values reduce scan time and improve results with smaller models |
| `workers` | int | No | Unset | Maximum concurrent CWE workers. Reduce when Ollama has limited parallelism (`OLLAMA_NUM_PARALLEL`) |

### Model Selection

Antares requires a model capable of multi-turn tool-use reasoning. Smaller models (2B parameters) will fail on most CWE investigations. Recommended minimums:

- **Production scans:** 7B+ model (e.g., `granite3-dense:8b`, `qwen2.5:7b`)
- **Quick validation:** 2B model with `max_cwes` set to 5-10

### Model Resolution Fallback

If you do not set `antares_inference.model`, Tally resolves the model using this chain (for Ollama only):

1. `antares_inference.model`, if explicitly set
2. `chat_inference.model` (if chat uses Ollama)
3. `triage_inference.model` (if triage uses Ollama)
4. `ollama.model` (base Ollama config)

For `llama_cpp` and `vllm`, only that provider's own config is checked.

### Example: Ollama

```json
{
  "ollama": {
    "base_url": "http://localhost:11434",
    "model": "granite3-dense:2b",
    "timeout_seconds": 60
  },
  "chat_inference": {
    "provider": "ollama"
  },
  "antares_inference": {
    "provider": "ollama",
    "timeout_seconds": 300
  },
  "antares_sweep_config": {
    "max_cwes": 15,
    "workers": 4
  }
}
```

When `antares_inference.model` is not set, Tally uses the chat model (`granite3-dense:2b` from the Ollama config).

### Example: Llama-server

```json
{
  "antares_inference": {
    "provider": "llama_cpp",
    "base_url": "http://localhost:8000",
    "model": "granite3-dense:2b",
    "timeout_seconds": 300
  }
}
```

---

## How Antares Runs

When you run a scan that includes Antares:

1. Tally resolves the Antares configuration and starts the completions shim (if Ollama is used)
2. Antares is invoked with environment variables pointing to the endpoint, model, and timeout
3. Antares explores the codebase, making completions requests to the endpoint
4. Antares outputs a JSON report with per-CWE findings and investigation traces
5. The shim (if running) is stopped, and findings are parsed and ingested

---

## Troubleshooting

### Connection refused

**Symptom:** Antares reports a connection error or timeout.

**Cause:** The endpoint is not reachable. Either Ollama is not running, or the `base_url` is incorrect.

**Fix:**
- Verify Ollama is running: `ollama serve` (or check your configured base_url if using llama-server or vLLM)
- Verify `base_url` matches your setup (default: `http://localhost:11434` for Ollama)
- If using a remote host, ensure the host is reachable and the port is open

### Model not found

**Symptom:** Antares reports "model not found" or similar error from the backend.

**Cause:** The model name does not exist on the server, or the model has not been pulled yet.

**Fix:**
- For Ollama, pull the model first: `ollama pull granite3-dense:2b`
- Verify the model name in `antares_inference.model` (or fallback chain) matches a model on the server
- For llama-server or vLLM, verify the model is loaded

### Slow startup

**Symptom:** First Antares inference request takes 30+ seconds.

**Cause:** Cold start. The model is being loaded into memory for the first time.

**Fix:** This is expected. Increase `timeout_seconds` if needed (default: `300`). Subsequent requests to the same model will be faster.

### Incomplete scan

**Symptom:** Antares scan completes but findings are fewer than expected, with a warning about failed workers or incomplete reason.

**Cause:** Antares workers timed out or encountered errors while investigating. May happen with low-resource systems or very large codebases.

**Fix:**
- Increase `timeout_seconds` to allow more time per request
- Reduce the scope (scan fewer CWEs or target fewer files)
- Allocate more resources to the model server (VRAM, CPU)
