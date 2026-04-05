# ADR-0005: nmap normalize() Produces One Row Per Open Port; One Row Per Up Host With No Open Ports

## Status
Accepted

## Date
2026-03-26

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

The original `NmapChunkBuilder.normalize()` only produced rows for open ports. A host that
was reachable (`state == "up"`) but had no open ports produced zero rows and was silently
dropped from the findings store. This created two problems:

1. A host sweep that confirmed a host was alive but had all ports filtered or closed
   produced no SQLite rows and no ChromaDB documents. From a security analyst perspective,
   a reachable host with no visible services is still a finding — it confirms the host
   exists on the network and may indicate firewall rules worth documenting.

2. `count_findings()` and `normalize()` returned consistent counts (both zero for hosts
   with no open ports), but the count was wrong from an analyst perspective: the host
   had been found, and the tool had confirmed its existence.

---

## Decision

`normalize()` applies the following rules per host:

- Host `state != "up"`: skip entirely — produce 0 rows.
- Host `state == "up"` with N open ports (N > 0): produce N rows, one per open port,
  each containing merged host-level fields (`ip_address`) and port-level fields
  (`port`, `transport`, `service`, `service_version`, `state`, etc.).
- Host `state == "up"` with 0 open ports: produce 1 row containing host-level fields
  only. The row has no `port`, `transport`, `service`, or `state` fields.

`count_findings()` in the nmap wrapper mirrors this: `max(open_port_count, 1)` per
"up" host.

`render()` branches on the presence of `row.get("port")`:
- Port present: renders full port detail line.
- Port absent: renders `"State: up (no open ports)"`.

---

## Alternatives Considered

### Always skip hosts with no open ports (previous behaviour)
Retain the original logic: only produce rows when open ports exist. Hosts that are up
but have no open ports are not represented in the findings store.

**Rejected because**: loses information about reachable hosts. An analyst querying "what
hosts responded to this sweep?" gets incomplete results. A host that is up with all ports
filtered is a security-relevant observation that belongs in the findings record.

### Aggregate all ports into a single row per host
Produce one row per host containing all open ports as a JSON array or comma-separated
list, rather than one row per port.

**Rejected because**: breaks the one-finding-per-row contract. Deduplication by
fingerprint becomes ambiguous when the port set changes across scans — an added port
would not produce a new row, and a closed port would not update an existing one cleanly.
The per-port row model allows each port's state to be tracked independently.

---

## Pros

- A host that is reachable but has no open ports is preserved in the findings record as
  an informational row, rather than being silently discarded.
- `count_findings()` and `normalize()` remain consistent in count across all host states.
- The one-row-per-port model supports per-port deduplication and fingerprinting (ADR-0006).

---

## Cons

- `render()` must handle the absence of the `port` field — this is a conditional branch
  checked by `row.get("port") is not None` that must be maintained whenever `render()` is
  modified.
- A host that transitions from no-open-ports to having open ports will leave the host-only
  row in place until the next delete-then-insert cycle (ADR-0002) clears it. The host-only
  row and the new port rows will coexist briefly after a rescan if the ChromaDB sync runs
  before the group-delete.

---

## Consequences

### Positive
- A host sweep of 10 hosts where 3 are up with no open ports now produces 3 SQLite rows
  and 3 ChromaDB documents, rather than 0 for those hosts.
- Analysts can query "all hosts that responded" and receive a complete picture, including
  hosts with no exposed services.

### Negative
- The host-only row uses a different schema subset from port rows — it has no `port`,
  `transport`, `service`, or `state` fields. Any code that assumes all nmap rows have
  these fields must use `row.get()` rather than direct key access.

### New Decisions Required
- A decision is needed on whether the host-only row should be removed when a subsequent
  rescan finds open ports on the same host, or whether it should remain as a historical
  record of the initial state.

---

## Influences

- The TAL-93 refactor that changed `NmapChunkBuilder.build()` to `normalize()`, during
  which the `"exposure"` regression (ADR-0009) and the silent host-drop bug were both
  identified and corrected.

---

## Related Decisions

- [ADR-0004: ToolHandler Protocol — normalize() and render()](./ADR-0004-tool-handler-protocol-normalize-and-render.md) — defines the normalize/render contract that this decision implements
- [ADR-0006: nmap Fingerprint Includes (ip_address, port, transport)](./ADR-0006-nmap-fingerprint-includes-ip-address-port-transport.md) — defines how host-only rows are deduplicated across scans
- [ADR-0009: nmap finding_type Is "informational"](./ADR-0009-nmap-finding-type-is-informational.md) — applies to all nmap rows including host-only rows

---

## Review Date

No review date — this decision reflects the fundamental contract between nmap scan output
and the findings store. Review only if the nmap output schema changes materially.
