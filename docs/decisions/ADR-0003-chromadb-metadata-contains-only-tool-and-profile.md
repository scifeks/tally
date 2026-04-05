# ADR-0003: ChromaDB Metadata Contains Only {tool, profile}

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

ChromaDB metadata fields are indexed and filterable at query time. Earlier designs stored
richer metadata — severity, ip_address, port, finding_type — in ChromaDB to enable
field-level filtering without touching SQLite. As the enrichment pipeline matured, these
fields became subject to post-ingest updates: the LLM enrichment pass writes severity,
remediation, and classification back to the SQLite row. Each update would require a
corresponding ChromaDB metadata patch to keep both stores in sync.

The central question was: which store owns finding metadata, and which store is the
derived index?

ADR-0001 established SQLite as the single source of truth. That decision implied that
ChromaDB metadata should not duplicate SQLite fields, because duplication creates a sync
obligation that grows with every enrichment update.

---

## Decision

ChromaDB document metadata is exactly `{"tool": str, "profile": str}`. No other fields.

All other finding data — severity, ip_address, port, service, finding_type, enrichment
output — lives in SQLite. Downstream queries that need enriched fields read them from
SQLite by joining on `str(findings.id)` == ChromaDB doc ID.

The two metadata fields (`tool`, `profile`) are retained because they are required by
ADR-0002's group-delete strategy and for tool-scoped retrieval in the RAG query path.

---

## Alternatives Considered

### Rich metadata in ChromaDB (severity, ip_address, port, finding_type)
Store a full subset of the SQLite row in ChromaDB metadata to allow field-level filtering
at ChromaDB query time without a SQLite join.

**Rejected because**: creates a second sync obligation alongside SQLite. Every enrichment
update to a SQLite row would require a corresponding ChromaDB metadata patch. Given that
enrichment can update severity, remediation text, and classification fields, the metadata
patch would need to run after every enrichment cycle — effectively making ChromaDB a
near-real-time replica of SQLite with no clear benefit, since SQLite already supports
structured queries directly.

### No metadata at all
Store documents with no metadata, relying solely on document IDs for retrieval.

**Rejected because**: the group-delete strategy in ADR-0002 requires `tool` and `profile`
to be queryable as metadata filters. Without them, scoping a delete to a specific
`(tool, profile)` pair would require scanning all document IDs, which is fragile and
non-performant.

---

## Pros

- ChromaDB metadata never goes stale relative to SQLite. Enrichment writes only to
  SQLite; ChromaDB embedding text is regenerated from the updated row via `render()` at
  the next sync, not from a separate metadata patch.
- The metadata schema is fixed and minimal — adding new SQLite columns for enrichment
  output never requires a ChromaDB migration.
- ChromaDB queries filtered by `tool` and/or `profile` remain possible for the most
  common retrieval pattern (tool-scoped RAG).

---

## Cons

- Field-level filtering on semantic attributes (e.g. `severity == "high"`, `port == 443`)
  cannot be done in ChromaDB. These queries must go to SQLite, which means the RAG path
  may require a pre-filter step that hits SQLite before or after the vector query.
- Any caller that assumed ChromaDB metadata contained richer fields must be updated to
  perform a SQLite join for those attributes.

---

## Consequences

### Positive
- ChromaDB embedding text always reflects the post-enrichment state of the SQLite row:
  `ChromaDBHandler` calls `render()` on the SQLite row, not on the original tool output.
- No schema migration is required in ChromaDB when SQLite columns are added or enrichment
  fields change.

### Negative
- Semantic search results from ChromaDB are IDs that must be resolved against SQLite to
  retrieve structured finding data. All RAG responses require a SQLite read after the
  vector query.

### New Decisions Required
- If the RAG query path requires pre-filtering on semantic attributes (e.g. "only search
  high-severity nmap findings"), a strategy is needed for whether to pre-filter in SQLite
  before the vector query or to post-filter ChromaDB results against SQLite.

---

## Influences

- ADR-0001 (SQLite as single source of truth): this decision is a direct corollary —
  if SQLite owns all finding data, ChromaDB metadata should not duplicate it.
- ADR-0002 (group-delete by tool and profile): requires `tool` and `profile` to be
  present in metadata, establishing the minimum viable metadata schema.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — establishes that ChromaDB is derived; this decision follows directly
- [ADR-0002: ChromaDB Write Uses Delete-Then-Insert Grouped by (tool, profile)](./ADR-0002-chromadb-write-uses-delete-then-insert-grouped-by-tool-profile.md) — the group-delete requires `tool` and `profile` metadata
- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — `render()` produces the ChromaDB embedding text from the SQLite row

---

## Review Date

Review if the RAG query path requires field-level pre-filtering on semantic attributes
that cannot be expressed as tool/profile filters, making the minimal metadata schema
a performance constraint.
