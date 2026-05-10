# ADR-0017 — Async Streaming LLM Adapter (Additive)

**Status:** Accepted  
**Date:** 2026-04-25  
**Deciders:** Scifeks  
**Influences:** Phase 8 (Chat) design session 2026-04-25; `chat-history.md`
decision 9; `roadmap.md` task 8.3  
**Related Decisions:** B7 (chat-history schema and lifecycle); Q3
(`global.json` not editable from UI); Q6 (`claude.api_key` not editable
from UI)

---

## Context

`roadmap.md` task 8.3 is described as a prerequisite "LLM adapter
architectural overhaul," and `chat-history.md` decision 9 calls for an
"async-first redesign" of `LLMProvider`, `OllamaAdapter`, and
`ClaudeAdapter`. The placeholder interface declared there is:

```python
async def stream_chat(
    self, messages: list[dict[str, str]], **kwargs: Any
) -> AsyncIterator[str]: ...
```

Both prior documents were written assuming Phase 8 would be a
ChatGPT-style chat application: token-by-token UX, billing/quota
tracking, and full async migration of every LLM caller in the
codebase.

The Phase 8 design session on 2026-04-25 narrowed the actual product:

1. Add `chat_sessions` / `chat_messages` SQLite tables so the existing
   single-turn RAG `chat` REPL command gains multi-turn-within-a-session
   *and* multiple resumable sessions per project.
2. Lift chat application logic out of the REPL adapter into a
   hexagonal application service.
3. Wire two adapters on top of that service: the REPL `chat` command
   (UX unchanged) and a new HTTP/FastAPI route for the React UI.

The actual chat product is RAG-over-ChromaDB summarised by the
configured LLM, with persistent history. Streaming is desired so that
words appear as the model produces them, but no other LLM caller
benefits from async (REPL dispatcher is sync; enrichment runs under
ThreadPoolExecutor; draft generation runs in a daemon thread; triage
shells out to the `claude` binary with a `.mcp.json` permissions
manifest).

The decision is whether 8.3 is a wholesale async-first rewrite of the
adapter layer (and migration of every caller) or a narrower, additive
change.

---

## Decision

Add a single new abstract method to `LLMProvider`:

```python
@abstractmethod
def stream_chat(
    self,
    messages: list[dict[str, str]],
    **kwargs: Any,
) -> AsyncIterator[str]:
    """Stream the model's reply as already-decoded UTF-8 text chunks."""
```

Implement it on both adapters (`ClaudeAdapter`, `OllamaAdapter`) using
each SDK's native async streaming API
(`anthropic.AsyncAnthropic.messages.stream(...)` and
`ollama.AsyncClient.chat(stream=True)`). Implementations are async
generators (`async def` with `yield`).

Existing sync methods (`is_available`, `complete`, `chat`) and existing
callers (REPL `chat`, REPL draft, REPL report, enrichment pipeline,
triage subprocess) are **not changed**.

Concrete commitments:

- Yields plain UTF-8 text chunks. No integer token IDs, no typed event
  union, no usage envelope.
- **Pass-through chunking** — each provider chunk forwarded verbatim;
  no server-side word-boundary buffering.
- `prompt_tokens` and `completion_tokens` columns are dropped from the
  Phase 8.1 `chat_messages` schema; `chat-history.md` and `roadmap.md`
  are updated accordingly.
- Cancellation flows via standard asyncio task cancellation
  (`aclose()` on the iterator). No custom `CancellationToken`
  parameter.
- Errors raised inside `stream_chat` are wrapped in
  `LLMAdapterError`. Sync `chat()` keeps existing behaviour.
- Triage subprocess (`application/triage/runner.py:461-474`) is out of
  scope. It is a separate adapter family with its own MCP-based
  security gates; converting it to an in-process Anthropic SDK call is
  a multi-session effort independent of the chat work.

---

## Alternatives Considered

### Full async-first rewrite of `LLMProvider` and every caller

Replace sync `chat()` / `complete()` with async equivalents; migrate
REPL `chat`, REPL draft, REPL report, enrichment, and triage to
`async/await`. Add a sync bridge (`asyncio.run(...)` wrapper) for
callers that cannot become async.

**Rejected:** No existing caller benefits. The REPL dispatcher is
inherently sync and the "REPL is immutable" rule rules out changing its
UX. Enrichment is CPU-bound and runs under a ThreadPoolExecutor; making
its inner LLM call async would force a sync bridge that adds nothing.
Migrating triage is a separate, larger problem (MCP tool exposure,
batch retry semantics). The work cost is substantial; the user-visible
benefit is zero.

### Stream typed event objects (`AsyncIterator[ChatChunk]`)

`stream_chat` yields a typed union: `TextChunk(text: str)` plus a final
`UsageChunk(prompt_tokens, completion_tokens, model)`.

**Rejected:** Phase 8.1 has no consumer for token counts. The schema
columns we would populate from the usage envelope are also being
dropped (D4 in `llm-adapter-design.md`). A typed-event interface is
strictly more complex than `AsyncIterator[str]` and delivers nothing
the simpler interface cannot.

### No streaming — batch the full response on the server

API POST runs the LLM in a worker thread and returns the complete
assistant message when done. UI shows a spinner during the wait. SSE
chat stream is dropped from `endpoints.md`.

**Rejected:** The user explicitly chose to surface incremental output
("words could maybe appear on screen 1 or more at a time"). Streaming
is not required for correctness, but the UX ask is explicit and the
implementation cost is small.

### Server-side word-boundary buffering

Buffer provider chunks until a whitespace or punctuation boundary,
then emit one event per word.

**Rejected:** Adds complexity for marginal UX improvement. The user
explicitly accepted mid-word fragments when the trade-off was framed.
Can be added later if it becomes annoying in practice.

---

## Pros

- Smallest diff that unblocks Phase 8 chat: one new abstract method,
  two implementations, three test files.
- Zero risk to existing callers; the REPL `chat` UX, draft generation,
  enrichment, and triage are byte-for-byte unchanged.
- Both SDKs already provide async streaming as a first-class API
  (`anthropic.AsyncAnthropic`, `ollama.AsyncClient`); no shimming
  required.
- Cancellation is free — Python's async generator protocol already
  propagates `aclose()` through the SDK's own cleanup paths.
- Reversible. If a future feature needs token counts, async sync
  callers, or a unified async interface, this ADR is replaced; nothing
  about the current design forecloses those moves.

## Cons

- The `LLMProvider` abstract surface now mixes sync and async methods.
  A reader unfamiliar with the design may infer that the codebase is
  async-first, which it is not.
- `prompt_tokens` / `completion_tokens` columns will be re-added to
  the schema if a future feature needs them, requiring a migration.
- The `event: token` SSE event name in `endpoints.md` is now a
  misnomer (the payload is plain UTF-8, not numeric tokens). The name
  is retained as established public-facing vocabulary, but it requires
  documentation to avoid confusing future maintainers.

---

## Consequences

### Positive

- Phase 8.1 (chat tables) and Phase 8.2+ (chat application service +
  HTTP route) can proceed without a blocking design session.
- Existing test suite (2975 passing as of 2026-04-25) is not perturbed.
- The Phase 8 chat HTTP handler can iterate `stream_chat` directly;
  no thread pool, no sync bridge, no double-buffering.

### Negative

- `LLMProvider` now has four abstract methods instead of three; any
  third-party adapter implemented in the future must provide
  `stream_chat` even if it is not used by the project the adapter is
  wired into.
- The "additive" decision means `chat()` and `stream_chat()` carry
  parallel kwarg-normalisation logic in each adapter. Mitigated by
  factoring the shared logic into private helpers
  (`_normalise_kwargs`, `_split_messages`) in the Claude adapter and
  `_build_options` in the Ollama adapter.

### New Decisions Required

- The Phase 8 chat HTTP route must decide its SSE event payload shape.
  Current recommendation: keep the `event: token` name from
  `endpoints.md` but document that the payload is `{"text": "..."}`
  containing already-decoded UTF-8.
- If a future caller (cost tracking, quota gating, debugging) needs
  prompt/completion token counts, a follow-up ADR is required to
  decide whether token counts are added back to the
  `LLMProvider`/`stream_chat` interface, populated post-hoc, or
  exposed via a separate `last_usage()` method.

---

## Review Date

2026-10-25 (six months). Revisit if any of the following becomes true
before then:

- A second async caller emerges that would benefit from a unified
  async interface.
- A user-facing feature requires token counts.
- Triage migrates off the subprocess path.

If none of those happen, the additive design is the right long-term
shape and this ADR can be marked `Stable` at the review date.
