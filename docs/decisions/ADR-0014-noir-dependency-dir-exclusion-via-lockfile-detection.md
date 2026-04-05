# ADR-0014: Exclude Noir Vendor Endpoints via Lockfile-Based Dependency Directory Detection

## Status
Accepted

## Date
2026-04-04

## Deciders
- Scifeks (project owner) — proposed and approved

---

## Context

OWASP Noir scans a repository's entire source tree via `-b <repo_path>`. For projects
that vendor their dependencies (PHP via Composer, Node via npm/yarn, Python via venv,
Go in vendor mode), the repository root contains the full source code of every
dependency — not just the application.

Noir performs static analysis across this entire tree and reports routes it finds
anywhere, including in framework and library code inside `vendor/`, `node_modules/`,
`.venv/`, etc. For php-goof, Noir reported 367 endpoints; only 10 were real application
endpoints. The remaining 357 were HTTP routes defined inside `vendor/` packages
(Symfony, Laravel, and other Composer dependencies).

This produced two visible problems:

1. **Inflated display counts**: `count_findings()` returned 367 for php-goof while only
   10 rows were written to SQLite — a discrepancy that an analyst querying the database
   would immediately notice and could not explain from the terminal output alone.
2. **Inaccurate summary table**: The scan summary table showed 655 total Noir findings
   across all DVPA repositories (summed), but the SQLite `findings` table contained only
   245 Noir rows.

A partial mitigation existed: `NoirHandler.normalize()` (the SQLite ingest handler)
filtered vendor paths using a hardcoded `_VENDOR_INDICATORS` set. This prevented vendor
endpoints from reaching SQLite but did not affect `count_findings()`, which ran against
raw parsed data and therefore returned the inflated pre-filter count. The two consumers
— display layer and ingest layer — applied incompatible views of the same parsed data.

A separate but related bug was also fixed in this work: the scan summary table was
accumulating `findings_by_tool` as a per-tool total across all repos, then assigning
that total to every row. Every Noir row showed 655 (the all-repos total) instead of the
per-repo count (7, 367, 38, 198, 38, 7). This is documented here because it shared the
same root cause (display layer consuming raw rather than normalised counts) and was
corrected in the same change.

---

## Decision

**Filter Noir endpoints inside `parse_output()`, before `parsed_data` is returned to
any consumer.** All downstream code — `count_findings()`, `NoirHandler.normalize()`, and
the summary display — receives only non-vendor endpoints. There is a single filtering
point; no consumer needs its own filter.

The filter is driven by **lockfile detection at `build_execution_passes` time**. For
each recognised package manager file (e.g. `composer.json`, `package.json`,
`requirements.txt`), the repo directory is checked for the corresponding dependency
directory. Only directories that actually exist on disk are excluded. Detected exclude
prefixes are stored on the tool instance (using the same `self._last_report_path` bridge
pattern already established for the OAS3 output file) and applied in `parse_output()`.

A static fallback (`is_vendor_or_dependency_path()` from `noir_parser.py`) is also
applied for dependency indicators not covered by the lockfile detection (e.g. a `vendor/`
directory without a `composer.json`).

The lockfile-to-directory mapping lives in a new module,
`infrastructure/tools/dependency_detection.py`, which is tool-agnostic and can be
reused by any future tool that scans source trees.

**The summary table aggregation bug is fixed separately** by adding a `finding_count`
field to `ToolResult`, set per-execution in `RepoSegmentScan`, and used instead of the
accumulated per-tool total when building summary table rows.

---

## Alternatives Considered

### Use Noir's `--use-filters` flag to suppress vendor endpoints at the CLI level
The `--use-filters` flag accepts URL/method patterns and is documented as a way to
exclude endpoints from Noir's output.

**Rejected because**: the `--use-filters` flag only applies to Noir's Deliver mode
(sending results to an external endpoint). It has no effect on the OAS3 file written
via `-f oas3 -o`. Verified against `noir --help` (v0.25.1).

### Scope `-b` to the application source subdirectory, not the repo root
Identify the application source directory (e.g. `src/`, `app/`) and pass that to
`-b` rather than the repo root, avoiding vendor directories entirely.

**Rejected because**: there is no reliable convention for which subdirectory contains
application code. Projects structure their source trees differently. Implementing
heuristic detection for this would be more fragile and harder to override than
simply excluding known dependency directories.

### Keep the existing post-parse filter in `NoirHandler.normalize()` only
The current mitigation — filtering in `normalize()` — already prevents vendor endpoints
from reaching SQLite. The divergence between display count and SQLite count could remain
a documented gap (as ADR-0008 established for the general case).

**Rejected because**: the gap for Noir was not a minor deduplication artefact but a
factor-of-36 difference for php-goof (367 displayed vs 10 stored). ADR-0008 accepts
divergence caused by fingerprint deduplication across runs; it does not accept
divergence caused by the display layer counting endpoints that are never ingested. The
two consumers applying incompatible views of the same data is a correctness problem, not
a known tradeoff.

### Apply the vendor filter in `noir_parser.py` (pure parser layer)
Filter vendor paths inside `_parse_oas3_data()` so that `parsed_data["endpoints"]` never
contains them in the first place, regardless of how the tool is invoked.

**Rejected because**: the parser module is pure data transformation with no filesystem
access. Determining which paths are vendor paths for a specific repository requires
knowing which dependency directories exist in that repository — a runtime concern, not a
parse-time concern. Hardcoding vendor path heuristics in the parser would mix two
concerns and make the parser harder to test in isolation.

---

## Pros

- `count_findings()` and `NoirHandler.normalize()` now see identical data. The display
  count matches the SQLite count (subject to cross-repo fingerprint deduplication, which
  is the only remaining source of divergence for Noir and is the accepted gap from
  ADR-0008).
- Exclusions adapt to the repository's actual ecosystem. A pure-Go repo that does not use
  Go vendor mode will not have `/vendor/` excluded; a PHP repo with `vendor/` will.
- The lockfile detection module is reusable. Any tool that scans source trees can call
  `detect_dependency_dirs()` without noir-specific logic.
- The static fallback ensures a `vendor/` directory without a `composer.json` is still
  excluded — covering cases where lockfiles are `.gitignore`d but the directory was
  committed.

---

## Cons

- Filtering happens at `parse_output` time, which runs inside the executor after the tool
  binary exits. If the OAS3 file is consumed by another tool (ZAP, via `_find_noir_oas3`)
  before `parse_output` runs, ZAP will still receive the unfiltered OAS3 spec and may
  scan vendor endpoints. This is a known limitation: the OAS3 passthrough to ZAP is not
  filtered by this change.
- The lockfile detection adds filesystem reads at `build_execution_passes` time — one
  `exists()` check per entry in `_LOCKFILE_TO_DEP_DIRS` (currently 13 entries). This is
  negligible but is a side effect introduced into a previously pure execution-pass builder.
- Instance state (`self._exclude_path_prefixes`) is reset in a `finally` block in
  `parse_output`. If `parse_output` is never called after `build_command` (e.g. the
  executor is subclassed and breaks the contract), the state leaks until the next
  invocation. This is the same risk that already exists for `_last_report_path`.

---

## Consequences

### Positive
- Analysts querying `SELECT COUNT(*) FROM findings WHERE tool = 'noir'` will now see
  counts that correspond to what the terminal reported for that run.
- ZAP scans are not affected by vendor endpoint inflation: ZAP does not read from SQLite
  for its target list; it reads the OAS3 file directly. ZAP was already scanning real
  endpoints; this change only corrects the count.
- The hardcoded `_VENDOR_INDICATORS` static list in `NoirHandler.normalize()` is removed;
  that logic now lives entirely in `NoirLocalTool.parse_output()` via the static fallback
  import from `noir_parser.py`.

### Negative
- The OAS3 file written to disk for ZAP consumption still contains vendor endpoints.
  A future change is needed to rewrite the OAS3 file after filtering if ZAP accuracy
  on vendor-containing repos becomes a concern.
- The `should_visualize = False` flag on Noir means vendor endpoint inflation was not
  visible in the findings browser. The fix is invisible to users who only use the UI —
  it surfaces only in the terminal count and direct DB queries.

### New Decisions Required
- The unfiltered OAS3 passthrough to ZAP is a known gap. A decision is needed on whether
  the filtered endpoint list should be written back to the OAS3 file before ZAP consumes
  it, or whether ZAP scanning vendor endpoints is acceptable given that real
  vulnerabilities in vendor code are typically out of scope for application testing.

---

## Influences

- The discovery that php-goof's Noir count (367) exceeded the total combined Noir + ZAP
  SQLite count (349) made the vendor inflation problem impossible to ignore.
- ADR-0008 explicitly deferred unifying display and SQLite counts. This change resolves
  the divergence for Noir specifically (the only tool where the gap was caused by
  correctness rather than deduplication).
- The `_last_report_path` bridge pattern established in the original Noir implementation
  (ADR-0012) provided the established mechanism for carrying state from
  `build_execution_passes` through to `parse_output` without modifying `ExecutionContext`
  or `ExecutionPass`.

---

## Related Decisions

- [ADR-0008: Scan Display Count Derived From count_findings()](./ADR-0008-scan-display-count-derived-from-count-findings.md) — this change narrows the divergence documented there for Noir specifically; the general gap between display and SQLite counts remains accepted for deduplication cases
- [ADR-0012: Noir as Pre-DAST Step with OAS3 File Passthrough to ZAP](./ADR-0012-noir-as-pre-dast-step-with-oas3-file-passthrough-to-zap.md) — the `_last_report_path` bridge pattern reused here; the unfiltered OAS3 passthrough to ZAP is a known gap from this change
- Future ADR needed: whether to filter the OAS3 file before ZAP consumes it (vendor endpoints currently reach ZAP's scanner)

---

## Review Date

Review if Noir adds an `--exclude-paths` CLI flag — at that point the lockfile detection
could drive a CLI argument instead of post-parse filtering, and the unfiltered OAS3
passthrough to ZAP would also be resolved.
