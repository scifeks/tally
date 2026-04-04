# ADR-0001: Use SQLite as the Single Source of Truth for Findings

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

The original architecture wrote findings directly from tool output to ChromaDB. ChromaDB was
the only persistent store. This created several compounding problems:

- Findings had no stable primary key — ChromaDB IDs were constructed ad hoc (e.g.
  `f"{profile}-{ip}:{port}"`)
- Enrichment metadata had nowhere normalised to live; attaching it to ChromaDB documents
  required a second write pass that re-used unstable IDs
- Re-runs had no deduplication strategy beyond replacing an entire ChromaDB collection,
  which destroyed findings from unrelated tools in the same collection
- The PATCH sync endpoint had no authoritative source to read from; it attempted to
  reconstruct state from ChromaDB, which contained only unenriched or partially enriched data

The absence of a relational store meant that any operation requiring cross-finding queries
(count by severity, filter by tool, paginated triage) had to be reconstructed from
ChromaDB document payloads — a vector store that is not designed for structured retrieval.

---

## Decision

SQLite is the single source of truth for all findings. ChromaDB is a derived index,
populated exclusively by reading from SQLite after enrichment is complete. No write path
goes directly to ChromaDB from tool output.

The event pipeline enforces this ordering:

```
ToolCompleted → IngestHandler (SQLite write)
             → IngestCompleted → EnrichmentHandler (SQLite update)
             → EnrichmentCompleted → ChromaDBHandler (ChromaDB write from SQLite rows)
```

ChromaDB doc IDs are always `str(findings.id)` — the SQLite primary key — ensuring they
are stable across re-runs for the same fingerprint.

---

## Alternatives Considered

### Write to both ChromaDB and SQLite simultaneously
Parse tool output once and fan out writes to SQLite and ChromaDB in the same handler.

**Rejected because**: two write paths create divergence. A partial failure leaves one store
ahead of the other with no recovery path short of a full rescan. One authoritative store
eliminates this class of inconsistency.

### Keep ChromaDB as the only store (status quo)
Continue writing directly to ChromaDB and fix ID stability separately.

**Rejected because**: ChromaDB provides no stable primary key, no row-level enrichment
storage, no structured query interface, and no deduplication primitive. These gaps cannot
be papered over without reimplementing a relational store inside ChromaDB.

---

## Pros

- Findings have stable integer primary keys (`findings.id`) that survive re-scans,
  enrichment updates, and ChromaDB rebuilds.
- The PATCH sync endpoint is trivially correct: read from SQLite, render to text, upsert
  to ChromaDB — a one-directional, idempotent operation.
- Any ChromaDB data loss or corruption is fully recoverable by re-running the sync from
  SQLite without triggering a new scan.
- Structured queries (count by severity, filter by tool, paginated triage) run against
  SQLite using standard SQL rather than reconstructing state from document payloads.

---

## Cons

- The pipeline is now sequenced: ChromaDB cannot be written until after SQLite ingestion
  and enrichment complete. Vector queries reflect only enriched findings; recently scanned
  but unenriched findings are not yet in ChromaDB.
- SQLite write throughput becomes the pipeline bottleneck under high scan volume. Current
  workload (~50 docs/minute) is well within SQLite's capacity, but concurrent scans may
  surface contention.
- Two stores must be kept operationally — SQLite for persistence, ChromaDB for vector
  search. A future simplification to a single store would require replacing ChromaDB's
  embedding and similarity-search capabilities.

---

## Consequences

### Positive
- ChromaDB is fully reconstructable from SQLite at any time; it can be treated as an
  expendable cache.
- Deduplication is handled at the SQLite layer via `ON CONFLICT (fingerprint) DO UPDATE`,
  meaning re-scans update existing rows rather than accumulating duplicates.
- Enrichment updates are atomic at the row level — a failed enrichment for one finding
  does not affect others.

### Negative
- Vector queries (semantic search, RAG) will not reflect findings that have been ingested
  to SQLite but not yet synced to ChromaDB.
- Any external tooling that previously wrote directly to ChromaDB must be updated to write
  to SQLite instead.

### New Decisions Required
- A decision is needed on SQLite write throughput strategy if concurrent scan volume
  increases substantially (e.g. WAL mode, connection pooling, or a queue-based ingest path).
- A policy is needed for how long unenriched findings sit in SQLite before alerting
  operators that the enrichment pipeline may be stalled.

---

## Influences

- The doc_id instability incident that preceded TAL-93, in which ChromaDB IDs changed
  across enrichment passes causing duplicate documents and broken PATCH sync behaviour.
- SQLite's ubiquity and zero-dependency deployment model — no additional infrastructure
  is required beyond the existing application server.

---

## Related Decisions

- [ADR-0002: ChromaDB Write Uses Delete-Then-Insert Grouped by (tool, profile)](./ADR-0002-chromadb-write-uses-delete-then-insert-grouped-by-tool-profile.md) — depends on this decision; ChromaDB is only written from SQLite
- [ADR-0003: ChromaDB Metadata Contains Only {tool, profile}](./ADR-0003-chromadb-metadata-contains-only-tool-and-profile.md) — follows from SQLite being the authoritative store for all other fields
- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — defines how tool output becomes SQLite rows

---

## Review Date

Review if scan volume exceeds 200 docs/minute sustained, or if SQLite write contention
becomes observable under concurrent scan workloads.
