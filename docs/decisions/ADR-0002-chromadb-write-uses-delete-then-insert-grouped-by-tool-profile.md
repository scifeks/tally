# ADR-0002: ChromaDB Write Uses Delete-Then-Insert Grouped by (tool, profile)

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

When a scan is re-run with fewer findings than the previous run — for example, a previously
open port is now closed, or a rotated secret no longer appears in the git history — stale
ChromaDB documents from the prior run must be removed. A pure upsert inserts new documents
and updates existing ones, but it cannot remove documents that are no longer present in the
current result set.

The group scope for cleanup must be precise: a rescan of `nmap` against `localhost` must
not disturb ChromaDB documents produced by `nmap` against `dmz`, or by `gitleaks` against
`localhost`. Both `tool` and `profile` are required to define the correct cleanup boundary.

---

## Decision

`ChromaDBHandler` groups the current batch of findings by `(tool, profile)`. For each
group it:
1. Deletes all existing ChromaDB documents where `metadata.tool == tool` AND
   `metadata.profile == profile`
2. Inserts the current batch for that group

This guarantees that after a scan, ChromaDB contains exactly the current findings for
that `(tool, profile)` pair — no more, no less.

---

## Alternatives Considered

### Pure upsert (insert-or-update)
Insert new documents and update existing ones by ID, leaving documents with no
matching ID in the new batch untouched.

**Rejected because**: cannot remove documents that are absent from the new result set.
A closed port or rotated secret would remain in ChromaDB indefinitely, producing stale
results in vector queries.

### Delete entire collection and rebuild
Drop the ChromaDB collection for the project and re-insert all findings from all
tools and profiles.

**Rejected because**: destroys findings from tools and profiles not included in the
current scan. A targeted nmap rescan must not remove gitleaks or semgrep findings.

### Track deleted IDs in SQLite
Maintain a deletion log in SQLite and apply it to ChromaDB during the sync phase.

**Rejected because**: adds a deletion-tracking mechanism that the group-delete strategy
renders unnecessary. The group-delete achieves the same outcome — a clean ChromaDB state
for the rescanned pair — without additional schema or write paths.

---

## Pros

- A rescan always produces a clean, current ChromaDB state for the `(tool, profile)` pair
  without manual cleanup or a deletion log.
- Findings from unrelated tool/profile pairs in the same collection are never touched —
  the delete is precisely scoped.
- The implementation is simple: one metadata-filtered delete followed by one batch insert.

---

## Cons

- The delete-then-insert is not atomic in ChromaDB. A crash between the delete and the
  insert leaves the collection temporarily empty for that `(tool, profile)` pair. Recovery
  requires re-running the ChromaDB sync from SQLite.
- All documents for the `(tool, profile)` pair are re-embedded on every rescan, even if
  most findings are unchanged. There is no incremental update path.

---

## Consequences

### Positive
- ChromaDB always reflects the most recent scan results for each `(tool, profile)` pair,
  without accumulating stale documents over time.
- The sync operation is idempotent: running it twice produces the same ChromaDB state.

### Negative
- Vector queries during the window between delete and insert will return zero results for
  the affected `(tool, profile)` pair. This window is short in practice but nonzero.
- Re-embedding all findings on every rescan has a cost proportional to finding count, not
  to the number of changed findings.

### New Decisions Required
- If scan frequency increases substantially, an incremental sync strategy (diff-based
  insert/delete) may be warranted to reduce re-embedding cost.

---

## Influences

- ADR-0001 (SQLite as single source of truth): ChromaDB is a derived index; the
  delete-then-insert pattern is safe precisely because SQLite is authoritative and
  ChromaDB can always be rebuilt.
- ADR-0003 (ChromaDB metadata contains only tool and profile): the group-delete relies
  on `tool` and `profile` being queryable metadata fields.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — ChromaDB is rebuilt from SQLite; the delete-then-insert is safe because SQLite is authoritative
- [ADR-0003: ChromaDB Metadata Contains Only {tool, profile}](./ADR-0003-chromadb-metadata-contains-only-tool-and-profile.md) — the group-delete filter requires `tool` and `profile` to be present in metadata

---

## Review Date

Review if ChromaDB is replaced by a vector store with transactional delete-and-insert
semantics, which would eliminate the non-atomic window. Also review if the re-embedding
cost on rescan becomes measurable at higher scan frequencies.
