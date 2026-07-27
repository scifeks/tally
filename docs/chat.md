# Chat

Tally provides RAG-augmented chat over ingested findings. You can ask
natural-language questions and get answers grounded in the active
project's knowledge base (ChromaDB retrieval + LLM generation).

Chat is available in two places:

- **REPL:** `chat <message>` runs a single-shot query against the
  active project's findings.
- **Web UI:** the SPA exposes a Chat tab when chat is enabled in
  `config/global.json`.

## Provider support

Chat works with any configured provider: `ollama`, `llama_cpp`,
`claude`, or `openai`. The SPA's Chat tab is shown when `chat_inference` is
configured in `config/global.json`. The capabilities probe (`GET
/api/v1/capabilities`) returns `chat_enabled: true` when
`chat_inference` is present.

Chat retrieval requires an embedding provider (`embedding_inference`) to encode
questions and findings for vector search. Supported embedding providers are
`ollama`, `llama_cpp`, and `voyage`. Voyage is embedding-only and cannot be
used for chat inference itself.

## Configuration

Chat requires two provider configurations: `chat_inference` for the LLM and
`embedding_inference` for vector retrieval. See
[docs/configuration.md](configuration.md) for the full `embedding_inference`
reference.

To enable chat, edit `config/global.json`:

1. Add a `chat_inference` feature config with your chosen provider:

   ```json
   {
     "chat_inference": { "provider": "ollama" }
   }
   ```

   Other providers are `"llama_cpp"`, `"claude"`, and `"openai"`.

2. Add an `embedding_inference` feature config for retrieval:

   ```json
   {
     "embedding_inference": { "provider": "ollama" }
   }
   ```

3. Configure the provider blocks with the model, host, and port:

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

4. If using the `ollama` provider, make sure Ollama is running and the
   configured models have been pulled:

   ```bash
   ollama pull qwen2.5:14b
   ollama pull nomic-embed-text
   ollama serve
   ```

   If using `llama_cpp`, start llama-server instead. If using `claude`,
   set the `ANTHROPIC_API_KEY` environment variable.

If `chat_inference` is absent or null in `config/global.json`, the SPA
hides the Chat tab and any direct call to the chat endpoints will fail.

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
The web UI supports creating, switching between, and deleting chat
sessions, and messages stream in real time.

## Document Ingest

By default, chat retrieves answers from your project's scan findings. You can
augment the RAG knowledge base with custom markdown or text documents using the
`docs` REPL command:

```
[acme-audit]> docs add runbooks/injection-fix-guide.md
[acme-audit]> docs list
[acme-audit]> docs remove runbooks/injection-fix-guide.md
```

Supported file types are `.md` and `.txt`. Documents are chunked and embedded
alongside findings, allowing chat to draw answers from both sources. This is
useful for providing custom runbooks, remediation guides, or domain-specific
context that improves answer quality. See [docs/repl.md](repl.md) for the
full `docs` command reference.

## Limitations

- **REPL is single-shot.** Each `chat` command is independent with no
  conversation history. The web UI supports persistent chat sessions
  with message history.
- **Per-project.** Chat answers are scoped to the active project's
  findings.
