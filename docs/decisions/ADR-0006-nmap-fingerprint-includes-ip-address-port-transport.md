# ADR-0006: nmap Fingerprint Includes (ip_address, port, transport); Host-Only Row Uses Empty Port/Transport

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

SQLite deduplicates findings via an `ON CONFLICT (fingerprint) DO UPDATE` upsert. The
fingerprint must uniquely identify a finding across scans so that re-scanning the same
target produces an update to the existing row rather than inserting a duplicate.

For nmap, the natural unique identifier for a finding is the combination of IP address,
port number, and transport protocol. Two distinct ports on the same host are different
findings; the same port rescanned produces an update.

ADR-0005 introduced a second row type: a host-only row for hosts that are up but have no
open ports. These rows have no port or transport fields. A fingerprint scheme that requires
all three fields would not apply cleanly to host-only rows without special-casing.

---

## Decision

The nmap fingerprint scheme (defined in `infrastructure/tools/fingerprints.py`) is:

```
"nmap|{ip_address}|{port}|{transport}"
```

For port rows: all three fields are populated from the scan output, e.g.
`"nmap|192.168.1.1|443|tcp"`.

For host-only rows (no open ports), `port` and `transport` are empty strings, producing:

```
"nmap|192.168.1.1||"
```

This is unique per IP address. If the same host appears in two scans with no open ports,
the second scan updates the existing row rather than inserting a duplicate.

The scheme requires no branching in the fingerprint function — the same template applies
to both row types, and empty strings naturally produce a distinct fingerprint that cannot
collide with any port row (port numbers are never empty strings).

---

## Alternatives Considered

### Separate fingerprint scheme for host-only rows
Use `"nmap|{ip_address}"` for host-only rows (omitting the trailing pipe characters).

**Rejected because**: the difference is cosmetic. Using the same template for both row
types with empty strings for absent fields achieves the same uniqueness guarantee without
a conditional branch or a second fingerprint format. Consistency is preferable.

---

## Pros

- A single fingerprint template handles all nmap row types without branching.
- Re-scanning a host with no open ports updates the existing host-only row rather than
  inserting a duplicate.
- The fingerprint is human-readable and self-describing: the tool, IP, port, and transport
  are all visible in the string.

---

## Cons

- The trailing `||` in host-only fingerprints is visually inconsistent with port-row
  fingerprints (`|443|tcp`). A developer reading the fingerprint table may find this
  confusing without knowing about host-only rows.
- If a host gains open ports on a re-scan, the host-only row (`nmap|192.168.1.1||`) and
  the new port rows (`nmap|192.168.1.1|80|tcp`) coexist in SQLite until the group-delete
  cycle removes the host-only row. During this window the host appears to have both a
  host-only record and port records.

---

## Consequences

### Positive
- Deduplication works correctly for all nmap row types using a single upsert path.
- No special-casing is required in `compute_fingerprint()` for the host-only case.

### Negative
- A host that transitions from no-open-ports to having open ports will temporarily have
  both a host-only row and port rows in SQLite. The host-only row will be removed on the
  next group-delete cycle (ADR-0002) when ChromaDB is synced.

### New Decisions Required
- If a future tool also has rows with optional fields that feed the fingerprint, a decision
  is needed on whether to standardise on the empty-string convention or introduce a null
  sentinel in fingerprint templates.

---

## Influences

- ADR-0005 (nmap normalize produces one row per open port, one row per up host with no
  open ports): introduced the host-only row type that required extending the fingerprint
  scheme.
- ADR-0001 (SQLite as source of truth): the `ON CONFLICT (fingerprint)` upsert is the
  deduplication mechanism that fingerprints enable.

---

## Related Decisions

- [ADR-0005: nmap normalize() Produces One Row Per Open Port](./ADR-0005-nmap-normalize-produces-one-row-per-open-port.md) — introduced the host-only row type that this fingerprint scheme accommodates
- [ADR-0001: SQLite as Single Source of Truth for Findings](./ADR-0001-sqlite-as-single-source-of-truth-for-findings.md) — the upsert deduplication that fingerprints support

---

## Review Date

No review date — the fingerprint scheme is stable as long as nmap output contains
ip_address, port, and transport fields. Review if the nmap output schema changes.
