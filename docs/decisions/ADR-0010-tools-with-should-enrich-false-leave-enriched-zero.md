# ADR-0010: Tools with should_enrich = False Leave enriched = 0 in SQLite

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

In the pre-TAL-93 (ChromaDB-only) architecture, `EnrichmentPipeline` called
`engine.update_metadata(doc_id, {"enriched": True})` for every document that was skipped
because the tool's `should_enrich = False`. This marked skipped documents as "done" in
ChromaDB to prevent future re-processing.

When the SQLite architecture was introduced (ADR-0001), the analogous SQLite write was
not added. The question arose: should `EnrichmentPipeline` call
`update_enrichment_fields(id, {})` to set `enriched = 1` for skipped tools, preserving
the old "done" marker behaviour?

The `enriched` column in SQLite has a different semantic from the `enriched` field in
ChromaDB metadata. In SQLite:

- `enriched = 1` means this row was processed by the LLM enrichment pipeline
- `enriched = 0` means this row was not processed by LLM enrichment

For tools that never use LLM enrichment (`should_enrich = False`), `enriched = 0` is
the accurate permanent state — no LLM call was ever made for this finding. Setting
`enriched = 1` via a no-op write would conflate "enrichment complete" with "enrichment
skipped", making the column meaningless as a pipeline state indicator.

---

## Decision

Tools with `should_enrich = False` (currently nmap and gitleaks) leave the `enriched`
column at `0` in SQLite after the pipeline runs. No `update_enrichment_fields` call is
made for them.

The `_get_enrichment_plan()` check (`should_enrich = False` → return `([], None)`) is
sufficient to prevent both LLM calls and SQLite writes for these tools. No additional
write path is added for the skipped case.

---

## Alternatives Considered

### Call update_enrichment_fields(id, {}) for skipped tools
Perform an empty update to set `enriched = 1` for tools that skip enrichment, matching
the old ChromaDB behaviour where skipped documents were marked as done.

**Rejected because**: would set `enriched = 1` for tools that were never LLM-enriched,
conflating "enrichment complete" with "enrichment skipped." Integration tests explicitly
assert that `update_enrichment_fields` must NOT be called for non-enriching tools and
that `enriched` must remain `0`. The old ChromaDB "done marker" behaviour had a different
purpose (prevent re-processing) that is not applicable in the SQLite architecture where
`should_enrich = False` is a static attribute, not a runtime state.

### Add an enriched_skipped column or value
Introduce a third state (e.g. `enriched = 2` or `enriched_skipped = True`) to
distinguish "enrichment not applicable" from "enrichment pending."

**Rejected because**: unnecessary complexity. The `should_enrich` attribute on the handler
is the source of truth for whether a tool supports enrichment. Downstream code that needs
to distinguish "not applicable" from "pending" can check the handler attribute rather than
a database column.

---

## Pros

- `enriched = 1` is a meaningful signal: it unambiguously means an LLM call was made
  for this row. No ambiguity between "enriched" and "skipped."
- No additional write path is needed in `EnrichmentPipeline` for the skipped case —
  the `([], None)` return from `_get_enrichment_plan()` is the complete implementation.

---

## Cons

- Downstream code filtering `WHERE enriched = 0` must understand that nmap and gitleaks
  rows are permanently `enriched = 0` — not enrichment-pending, but enrichment-not-applicable.
  Without this context, a "unenriched findings" query will incorrectly include nmap and
  gitleaks rows.

---

## Consequences

### Positive
- nmap and gitleaks findings permanently have `enriched = 0`. No re-enrichment attempts
  will be made for them.
- `enriched = 1` rows are definitively LLM-processed. The column can be used as a
  reliable indicator for post-enrichment queries.

### Negative
- A bulk query for "findings awaiting enrichment" (`WHERE enriched = 0`) will incorrectly
  include nmap and gitleaks rows. Callers must additionally filter by tool name or join
  against a list of enrichable tools.

### New Decisions Required
- A decision is needed on whether the findings query API should expose a
  "pending enrichment" filter that internally excludes non-enriching tools, rather than
  relying on callers to know which tools are non-enriching.

---

## Influences

- ADR-0001 (SQLite as source of truth): the `enriched` column in SQLite is the
  pipeline state indicator; the old ChromaDB `enriched` metadata field had a different
  semantic.
- The integration test suite for TAL-93, which explicitly asserted the no-write behaviour
  and guided the decision by failing when the no-op write was present.

---

## Related Decisions

- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — the SQLite `enriched` column is the pipeline state indicator
- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — `should_enrich` is an attribute on the handler, not the row

---

## Review Date

Review if a new tool is added whose enrichment applicability is dynamic (e.g. enrichable
for some finding types but not others), which would require a more nuanced enrichment
state model.
