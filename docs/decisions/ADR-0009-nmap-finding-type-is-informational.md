# ADR-0009: nmap finding_type Is "informational", Not "exposure"

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

During the TAL-93 refactor of `NmapChunkBuilder.build()` → `normalize()`, the
`type_flags` class attribute and the hardcoded `finding_type` field were inadvertently
changed from `"informational"` to `"exposure"`. This was a regression introduced while
changing the method signature — the semantic intent of nmap findings was not intended to
change.

nmap is a network reconnaissance tool. Its output consists of factual observations: this
host is reachable at this address; this port is open on this transport; this service
version is reported. nmap does not assess whether a finding represents a risk, a
misconfiguration, or an exploitable condition. An `"exposure"` finding_type implies that
the scanner has assessed and classified a risk — nmap does not do this.

The dev branch throughout TAL-93 used `finding_type = json.dumps(["informational"])`.
The regression conflated the act of discovering a finding with the act of classifying it
as an exposure.

---

## Decision

nmap findings use `finding_type = json.dumps(["informational"])` and
`type_flags = {"informational": set()}`.

The `_shared_meta(self, "informational")` call with an empty set means all `type_*`
boolean columns are `False` — including `type_informational`. The classification is
communicated through the `finding_type` JSON field only, not through boolean flags.
This matches the dev branch behaviour and the semantic intent of nmap output.

---

## Alternatives Considered

### Use type_flags = {"informational": {"type_informational"}}
Set `type_informational = True` in all nmap rows by populating the type_flags set,
consistent with how other tools use the boolean flag columns.

**Rejected because**: the dev branch used an empty set throughout, and changing it
would alter the boolean flag output for all existing nmap findings, causing test
assertion failures and potentially affecting downstream queries that filter on
`type_informational`. The `finding_type` JSON field is sufficient to classify nmap
findings without the boolean redundancy.

### Keep finding_type = "exposure"
Accept the regression and reclassify nmap findings as exposures.

**Rejected because**: nmap reports facts about network topology and service availability.
It does not assess risk. Classifying its output as "exposure" is semantically incorrect —
an exposure implies an analyst has evaluated a condition and judged it to represent a
risk surface. nmap makes no such assessment.

---

## Pros

- The `finding_type` field accurately reflects what nmap does: it discovers and reports,
  not assesses and classifies.
- Downstream triage workflows that filter on `finding_type` will not treat nmap rows as
  actionable vulnerability findings.
- Consistent with the dev branch: no surprise behaviour change for existing consumers.

---

## Cons

- `type_informational` boolean is `False` for nmap rows even though `finding_type`
  contains `"informational"`. A developer who expects the boolean to mirror the JSON field
  will find the relationship non-obvious and must understand the `type_flags` / `_shared_meta`
  pattern.
- The `finding_type` JSON field and the boolean `type_*` columns are partially redundant.
  Their relationship is not self-documenting in the schema.

---

## Consequences

### Positive
- All nmap rows in SQLite have `finding_type = '["informational"]'` and all `type_*`
  booleans `False`.
- Any downstream query filtering on `type_exposure = True` will correctly exclude nmap
  findings from exposure-only views.

### Negative
- A query filtering on `type_informational = True` will also exclude nmap findings,
  despite their `finding_type` containing `"informational"`. Callers must use
  `finding_type` as the authoritative classification for nmap rows.

### New Decisions Required
- A decision is needed on whether `finding_type` or the `type_*` boolean columns should
  be the canonical classification interface for downstream queries. The current state
  (nmap uses `finding_type` exclusively) is a partial answer.

---

## Influences

- The TAL-93 refactor that changed the `NmapChunkBuilder` method signature, during which
  the regression was introduced and subsequently caught.
- The dev branch behaviour, which served as the reference implementation for what nmap
  findings should look like in SQLite.

---

## Related Decisions

- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — `normalize()` is where `finding_type` and `type_flags` are set
- [ADR-0005: nmap normalize() Produces One Row Per Open Port](./ADR-0005-nmap-normalize-produces-one-row-per-open-port.md) — applies to all nmap row types including host-only rows

---

## Review Date

Review if the `type_*` boolean columns are unified with the `finding_type` JSON field
into a single classification interface, which would resolve the current inconsistency
for nmap rows.
