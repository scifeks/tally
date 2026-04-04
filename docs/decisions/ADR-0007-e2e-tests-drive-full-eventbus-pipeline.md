# ADR-0007: E2E Tests Drive the Full EventBus Pipeline

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

Prior e2e tests used a local `_ingest()` helper that called `engine.add_documents()`
directly. This approach bypassed `IngestHandler` (the SQLite write), `EnrichmentHandler`,
and `ChromaDBHandler` entirely. Tests asserted on ChromaDB query results without exercising
the pipeline that produced those results.

The consequence was that the actual pipeline could be broken while all e2e tests continued
to pass — the tests were verifying the test helper, not the system under test. When the
TAL-93 refactor introduced SQLite as the source of truth (ADR-0001), the broken pipeline
became visible: the `_ingest()` shortcut had hidden the fact that `IngestHandler` was
not wiring correctly.

---

## Decision

All e2e tests drive the pipeline by dispatching a `ToolCompleted` event onto a real
`EventBus` with all three handlers wired:

```python
bus = EventBus()
bus.subscribe(ToolCompleted, IngestHandler(bus).handle)
bus.subscribe(IngestCompleted, EnrichmentHandler(bus).handle)
bus.subscribe(EnrichmentCompleted, ChromaDBHandler().handle)
bus.dispatch(ToolCompleted(result, profile, None, project_name, str(base_path)))
```

`IngestCompleted.ids` are captured by a subscriber to verify the SQLite row count. Tests
then assert separately on SQLite count, ChromaDB doc count, and query output — three
independent checkpoints that each layer of the pipeline is functioning.

---

## Alternatives Considered

### Mock individual handlers
Replace `IngestHandler`, `EnrichmentHandler`, or `ChromaDBHandler` with mocks that
record calls and assert on arguments.

**Rejected because**: mocking handlers defeats the purpose of e2e tests. The prior
incident — where `_ingest()` bypassed SQLite and tests passed while the pipeline was
broken — is the exact failure mode that handler mocking would repeat. E2e tests exist
to verify that real handlers wire and execute correctly.

### Separate SQLite and ChromaDB test layers without a full e2e suite
Cover ingest in integration tests, ChromaDB writes in separate integration tests, and
skip e2e tests that run the full chain.

**Rejected because**: integration tests for individual handlers do not catch wiring bugs
between handlers. The `IngestCompleted` event must carry the correct IDs for
`EnrichmentHandler` to process the right rows; only an end-to-end test that dispatches a
real `ToolCompleted` event can verify this contract.

---

## Pros

- E2e tests catch pipeline wiring bugs (wrong event types, missing subscriptions, incorrect
  ID propagation) that unit and integration tests cannot observe.
- Three-checkpoint assertions (SQLite count, ChromaDB doc count, query output) pinpoint
  which layer of the pipeline failed when a test breaks.
- The `EventBus` setup in e2e tests mirrors the production wiring exactly — no special
  test configuration required beyond swapping in a test database path.

---

## Cons

- E2e tests are slower: they require a running Ollama instance for embedding generation
  and perform real SQLite writes and ChromaDB upserts. The `@requires_ollama` marker
  gates these tests in environments without a local Ollama instance.
- Any change to the event chain (new event type, new handler, changed subscription order)
  must be reflected in the e2e test setup. The setup is not automatically derived from
  the production wiring.

---

## Consequences

### Positive
- The full pipeline — from `ToolCompleted` dispatch through SQLite ingest, LLM enrichment,
  and ChromaDB sync — is exercised in tests. Regressions in any layer are caught before
  merge.
- The `@requires_ollama` marker enables selective CI: environments with Ollama run the
  full e2e suite; environments without it run unit and integration tests only.

### Negative
- E2e tests depend on Ollama availability. A developer without a local Ollama instance
  cannot run the full test suite. The `@requires_ollama` skip is a workaround, not a
  solution.

### New Decisions Required
- A decision is needed on whether e2e tests should be gated behind a separate CI stage
  that provisions an Ollama instance, or whether the `@requires_ollama` skip is sufficient
  for the team's workflow.

---

## Influences

- The prior `_ingest()` shortcut incident, which demonstrated that e2e tests bypassing
  the real pipeline provide false confidence.
- ADR-0001 (SQLite as source of truth): the three-stage pipeline (ingest → enrich →
  sync) that e2e tests must exercise end-to-end.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — the pipeline that e2e tests verify
- [ADR-0008: scan Display Count Derived From count_findings()](./ADR-0008-scan-display-count-derived-from-count-findings.md) — the `IngestCompleted.ids` count captured in e2e tests is distinct from the display count

---

## Review Date

Review if the EventBus wiring is extracted into a factory or fixture shared between
production and test code, which would eliminate the risk of test setup diverging from
production wiring.
