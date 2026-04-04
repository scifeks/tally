# ADR-0008: scan Display Count Derived From count_findings(); SQLite Count From IngestCompleted.ids

## Status
Accepted — divergence is a known gap, not treated as a bug for now

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

Two counts are tracked and displayed after a scan:

1. **Display count** — `count_findings(parsed_data)`, computed from raw parser output
   before any SQLite write occurs. This is the count shown in the terminal scan summary.
2. **SQLite count** — `len(IngestCompleted.ids)`, computed after the SQLite upsert
   completes. This reflects the number of rows actually written or updated in the store,
   with deduplication applied.

These counts can diverge in two scenarios:

- `IngestHandler` raises silently during the upsert. The display count shows N findings,
  but SQLite has 0. The terminal gives no indication of the failure.
- Fingerprint deduplication collapses multiple raw findings into fewer rows. A tool
  reports 5 findings, but 3 are updates to existing rows and 2 are new inserts. The
  display count is 5; the SQLite count reflects only new/updated rows depending on how
  `ids` is computed.

The two counts serve genuinely different purposes: the display count answers "what did
the tool observe in this run?", while the SQLite count answers "what changed in the
store?".

---

## Decision

Accept the divergence for now. The display count continues to be derived from
`count_findings(parsed_data)` at tool output time. The SQLite count in
`IngestCompleted.ids` is available in the event stream but is not surfaced in the
terminal display for TAL-93.

A future ticket may unify the counts by reading `IngestCompleted.ids` for the terminal
display, but that change is not in scope for TAL-93.

---

## Alternatives Considered

### Use IngestCompleted.ids as the display count
Wait for the `IngestCompleted` event and display `len(ids)` in the terminal summary
instead of the pre-ingest `count_findings()` result.

**Not implemented for TAL-93**: requires the display layer to subscribe to
`IngestCompleted` and update the terminal after the async upsert completes. This adds
latency to the terminal display and requires a UI update mechanism not currently present
in the scan output path. Deferred to a future ticket.

### Assert that both counts match and fail visibly if they diverge
Compare `count_findings()` and `len(IngestCompleted.ids)` after each scan and log a
warning or raise if they differ beyond a threshold.

**Not implemented for TAL-93**: useful as a diagnostic, but adds complexity for a case
(deduplication causing a lower SQLite count) that is correct behaviour, not an error.
A finding that matches an existing fingerprint is correctly counted as 1 by the tool
but 0 new inserts by SQLite. Treating this as a warning would produce false alerts on
every rescan.

---

## Pros

- The display count is available immediately after tool output is parsed, before the async
  ingest pipeline completes. No UI blocking or event subscription required for the terminal
  display.
- The documented divergence is an honest representation of the system's current state
  rather than a hidden inconsistency.

---

## Cons

- If `IngestHandler` fails silently, the terminal shows N findings while SQLite has 0.
  The analyst has no indication that the findings were not persisted. This is the primary
  risk of the accepted gap.
- The display count is the tool's view of its output, not the store's view. An analyst
  who correlates the terminal count with a database query may see different numbers.

---

## Consequences

### Positive
- Scan output is displayed immediately without waiting for SQLite writes to complete.

### Negative
- Silent `IngestHandler` failures produce a misleading terminal display. Monitoring for
  this failure mode requires log inspection, not UI observation.

### New Decisions Required
- A future ticket should decide whether to surface `IngestCompleted.ids` in the terminal,
  or to add an explicit error indicator when `IngestHandler` raises.
- A decision is needed on alerting when the display count and SQLite count diverge beyond
  what deduplication alone would explain.

---

## Influences

- The TAL-93 refactor that introduced the event-driven pipeline: `count_findings()` was
  already in use for the terminal display before SQLite was introduced, and changing
  the display path was not in scope.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — `IngestCompleted.ids` originates from the SQLite upsert
- [ADR-0007: E2E Tests Drive the Full EventBus Pipeline](./ADR-0007-e2e-tests-drive-full-eventbus-pipeline.md) — e2e tests capture `IngestCompleted.ids` to assert on the SQLite count independently of the display count

---

## Review Date

Review when the terminal scan summary is next modified — that is the natural point to
unify the display count with `IngestCompleted.ids`.
