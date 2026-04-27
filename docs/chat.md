# Chat

Tally provides RAG-augmented chat over ingested findings. You can ask
natural-language questions and get answers grounded in the active
project's knowledge base (ChromaDB retrieval + LLM generation).

Chat is available in two places:

- **REPL** — `chat <message>` runs a single-shot query against the
  active project's findings.
- **Web UI** — the SPA exposes a Chat tab when chat is enabled in
  `config/global.json`.

## Provider support

**Ollama is the only chat provider currently supported.** The SPA's
Chat tab is gated on this and will be hidden if chat is not configured
correctly. The capabilities probe (`GET /api/v1/capabilities`) returns
`chat_enabled: false` when the conditions below are not met.

Other roles (enrichment, report drafting, embeddings) can still use
Claude or Ollama independently — only the chat role is restricted.

## Configuration

To enable chat, edit `config/global.json`:

1. Set the chat provider to Ollama:

   ```json
   {
     "chat_llm_provider": "ollama"
   }
   ```

2. Configure the `ollama` provider block with the model, host, and
   port for your Ollama runtime:

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

3. Make sure Ollama is running and the configured model has been
   pulled:

   ```bash
   ollama pull qwen2.5:14b
   ollama serve
   ```

If `chat_llm_provider` is empty, missing, or set to anything other than
`"ollama"`, the SPA hides the Chat tab and any direct call to the chat
endpoints will fail.

## Usage

### REPL

```
[acme-audit]> chat What injection findings did we get from semgrep?
```

The REPL retrieves the top-K most relevant findings from ChromaDB,
sends them to the configured chat model along with the question, and
prints the response.

### Web UI

Run `ui serve` from the REPL to start the Web UI, then open the Chat
tab. The SPA queries the same project knowledge base used by the REPL.

## Limitations

- **Stateless.** Each chat message is independent; there is no
  conversation history yet.
- **Per-project.** Chat answers are scoped to the active project's
  findings.
- **Provider-locked.** Claude is not supported as a chat provider at
  this time.
