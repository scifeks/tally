# ADR-00014 — Discovery tools run before scanners within the web segment

**Status:** Accepted
**Date:** 2026-04-13
**Supersedes:** ADR-00013 §Decision item 3 ("no additional ordering logic is required")

---

## Context

ADR-00013 established that tools within the `web` segment run in
alphabetical order, and that this guarantee was sufficient because `noir <
zap` alphabetically. It explicitly deferred the question of additional
ordering logic to a future ADR.

Katana has been added as a second URL-discovery tool (alongside Noir).
Alphabetical ordering within `web` produces:

```
dalfox < katana < noir < xsstrike < zap
```

This means **DalFox runs before Katana on a first scan**. DalFox in
`katana` or `auto` mode looks for a Katana OAS3 file to build its seeds
list. When Katana has not yet run, no such file exists, and DalFox skips
the scan entirely — a silent, non-obvious failure.

The same problem affects XSStrike in `katana`/`auto` mode (falls back to
weak `--crawl` instead of targeted seeds) and ZAP (falls back to
spider-only instead of OpenAPI mode).

## Decision

Introduce `is_discovery_tool: bool = False` as a non-abstract property on
`ToolInterface`. Override it to `True` on `BaseKatanaTool` and
`BaseNoirTool`.

Modify `ordered_repo_tools()` in
`application/tools/scan_types/execution.py` to stable-sort each segment's
tool list so that `is_discovery_tool == True` tools appear first,
alphabetically within each group. The sort key is:

```python
key=lambda n: (not tool.is_discovery_tool, n)
```

This produces the following execution order for a full `web` segment scan:

```
katana, noir, dalfox, xsstrike, zap
```

Discovery tools remain alphabetical among themselves (`katana < noir`).
Scanners remain alphabetical among themselves (`dalfox < xsstrike < zap`).

## Consequences

- **All other segments are unaffected.** No currently-registered tool in
  any other segment sets `is_discovery_tool = True`, so their sort is
  purely alphabetical as before.
- **The `noir < zap` guarantee from ADR-00013 is preserved** as a
  side-effect: both are in the `web` segment, Noir is a discovery tool,
  ZAP is not.
- **New discovery tools** added in the future must set
  `is_discovery_tool = True` on their base class to participate in the
  ordering guarantee. The default is `False` (conservative — new tools
  run as scanners unless explicitly declared otherwise).
- **Alphabetical ordering within each group** is preserved so the overall
  ordering remains deterministic and testable without relying on set
  iteration order.

## Alternatives considered

**Keep alphabetical order, change tool names.** Renaming `dalfox` to
`xdalfox` to force `katana < xdalfox` alphabetically would be a hack that
breaks user-facing configuration and documentation. Rejected.

**Run all discovery tools as a separate pre-phase.** Would require a
two-pass executor loop and additional orchestration complexity. The
stable-sort approach achieves the same outcome with a single change to
`ordered_repo_tools()`. Rejected.

**Merge Katana and Noir output before scanners run.** Valuable for
deduplication but independent of ordering; can be added later without
changing this decision.

## Related decisions

- ADR-00013: `web` segment, alphabetical ordering, Noir before ZAP
