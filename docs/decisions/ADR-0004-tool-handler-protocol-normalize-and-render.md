# ADR-0004: ToolHandler Protocol — normalize() + render()

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

Each security tool in tally produces structurally different output. nmap emits XML with
nested host/port elements; gitleaks emits a JSON array of secret matches; semgrep emits
a JSON object with a `results` array of rule matches. The pipeline needs a uniform
interface to:

1. Convert raw tool output into SQLite-compatible row dicts (the ingest step)
2. Convert SQLite rows into embedding text for ChromaDB (the sync step)

These two operations were previously conflated in a single `build()` method inherited from
`BaseChunkBuilder`. Under the ChromaDB-only architecture, `build()` produced `(id, text,
metadata)` tuples that were written directly to ChromaDB. When SQLite was introduced as
the source of truth (ADR-0001), the single-method approach collapsed: the ingest step
needed row dicts suitable for SQLite, while the ChromaDB step needed text generated from
the post-enrichment SQLite row — not from the original tool output.

---

## Decision

Every tool handler implements two methods:

- `normalize(result: ToolResult, profile: str) -> list[dict]`: converts raw tool output
  into a flat list of SQLite-compatible row dicts. One dict per finding. Called by
  `IngestHandler` at ingest time.
- `render(row: dict) -> str`: converts a single SQLite row dict into the text string that
  is embedded and stored in ChromaDB. Called by `ChromaDBHandler` at sync time, after
  enrichment has updated the SQLite row.

The separation means that `render()` always receives the post-enrichment row from SQLite,
so ChromaDB embedding text reflects enriched data — not the raw tool output at ingest time.

---

## Alternatives Considered

### Single method returning (row, text) tuples
Have each handler implement `build() -> list[tuple[dict, str]]` returning SQLite row and
embedding text together in one pass.

**Rejected because**: embedding text must reflect the post-enrichment state of the row,
but enrichment runs after ingest. A single-pass method that produces both the row and its
text at ingest time would embed unenriched data. Separating the two steps allows
`ChromaDBHandler` to call `render()` on the post-enrichment row read back from SQLite.

### Generate embedding text at enrichment time
Have `EnrichmentHandler` produce and store the embedding text in SQLite alongside the
enrichment fields, so `ChromaDBHandler` reads pre-generated text.

**Rejected because**: couples the embedding format to the enrichment pipeline. Tools that
skip enrichment (`should_enrich = False`) would need a separate path to produce embedding
text, recreating the same problem. `render()` as a separate method keeps the embedding
logic encapsulated in the handler regardless of enrichment status.

---

## Pros

- ChromaDB document text always reflects the post-enrichment state of the SQLite row,
  never the raw unenriched tool output.
- Adding a new tool requires implementing exactly two well-scoped methods with clear
  contracts, rather than a monolithic builder.
- `normalize()` and `render()` can be tested independently: unit tests for `normalize()`
  verify row structure; unit tests for `render()` verify text formatting.

---

## Cons

- Implementing a new handler requires understanding the two-phase contract. A developer
  unfamiliar with the pipeline might conflate ingest-time and sync-time concerns.
- `render()` receives a row dict (SQLite representation) rather than a typed domain
  object. Field presence and types must be validated inside `render()` or handled via
  `row.get()` with defaults.

---

## Consequences

### Positive
- The ingest path and the ChromaDB sync path are independently testable and independently
  evolvable. Changing how a tool formats its embedding text does not require touching
  ingestion logic.
- `ChromaDBHandler` is tool-agnostic: it calls `render()` on whatever handler is
  registered for the finding's tool, without knowing the tool's output format.

### Negative
- Two passes over the data are required per scan cycle: one at ingest time (`normalize()`)
  and one at sync time (`render()`). For high-volume tools this adds processing time,
  though in practice the SQLite read at sync time is the bottleneck, not the `render()`
  call itself.

### New Decisions Required
- A decision is needed on whether `render()` should receive a typed domain object or
  continue to receive a raw dict. A typed object would catch missing fields at
  construction time rather than at render time.

---

## Influences

- ADR-0001 (SQLite as source of truth): the two-phase split follows directly from the
  decision to decouple ingest from ChromaDB sync.
- ADR-0003 (minimal ChromaDB metadata): `render()` produces the full embedding text;
  structured fields are in SQLite and not in ChromaDB metadata.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — the two-phase protocol exists because SQLite and ChromaDB are written in separate pipeline stages
- [ADR-0005: nmap normalize() Produces One Row Per Open Port](./ADR-0005-nmap-normalize-produces-one-row-per-open-port.md) — applies this protocol to the nmap handler
- [ADR-0009: nmap finding_type Is "informational"](./ADR-0009-nmap-finding-type-is-informational.md) — applies to the metadata produced by `normalize()`

---

## Review Date

Review if a typed domain object layer is introduced between raw tool output and SQLite
row dicts, which would change the contract for both `normalize()` and `render()`.
