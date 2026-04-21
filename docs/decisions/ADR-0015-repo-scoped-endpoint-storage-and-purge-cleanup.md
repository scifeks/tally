# ADR-0015: Repo-scoped endpoint file storage and purge cleanup of merged URL artifacts

## Status
Accepted

## Date
2026-04-20

## Deciders
- Justin (sole developer) — identified bugs, specified target layout, approved and implemented

---

## Context

Tally supports attaching a user-provided endpoint definition file (OAS3, OAS2,
Postman, HAR, or Katana JSONL) to a repository. The file is normalised to OAS3
and stored on disk so that subsequent scans (ZAP, DalFox, XSStrike) can consume
it. During a scan, Noir and Katana crawl output is merged with the user-provided
seed to produce two derived artifacts: a merged OAS3 document (consumed by ZAP
via `-openapifile`) and a plain-text URL list (consumed by DalFox and XSStrike).

Two bugs were identified:

**Bug 1 — no repo namespacing for user-provided seeds.** All five converter
adapters wrote their output to `output_dir / "endpoints.json"`, and
`wizard.py` computed `output_dir` as
`projects/<project>/endpoints/` — a single flat directory shared across all
repos in the project. In a multi-repo project, each `repo add` or `repo edit`
overwrote the same `endpoints.json`, leaving only the last repo's seed on disk.
The `repo edit` replace branch made this worse: it globbed
`endpoints/original/*` and unlinked anything that wasn't the new file —
deleting the original files of every other repo in the project.

**Bug 2 — purge did not clean up merged URL artifacts.** The merged outputs
were written to `projects/<project>/config/urls/<repo>_seeds.txt` and
`<repo>_merged_oas3.json`. Purge cleared RAG documents, SQLite findings, and
tool output files, but never touched the `config/urls/` directory or the
`merged_seeds_path` / `merged_oas3_path` keys in `project.json`. After purge,
stale merged files and their path references persisted indefinitely.

The `config/urls/` location was also semantically wrong: those files are
*derived scan artifacts*, not configuration, yet they sat inside `config/`.

---

## Decision

We reorganised the on-disk layout so that every endpoint artifact is scoped to
its repo, and we added an opt-in purge prompt to clean up merged URL artifacts.

**New layout:**

| Artifact | Path |
|---|---|
| Raw user seed (original) | `projects/<project>/config/endpoints/<repo>/original/<basename>` |
| Normalised OAS3 seed | `projects/<project>/config/endpoints/<repo>/seed.json` |
| `project.json` `oas3_path` | absolute path to `seed.json` above |
| Merged OAS3 (ZAP) | `projects/<project>/endpoints/<repo>/merged_oas3.json` |
| Merged URL list (DalFox / XSStrike) | `projects/<project>/endpoints/<repo>/merged_urls.txt` |
| `project.json` `merged_oas3_path` | absolute path to `merged_oas3.json` above |
| `project.json` `merged_seeds_path` | absolute path to `merged_urls.txt` above |

`config/endpoints/` is durable config that survives purge. `endpoints/` holds
derived scan output that purge may optionally clear.

**Changes made:**

- All five converter adapters (`oas3`, `oas2`, `postman`, `har`, `katana`) now
  write `seed.json` instead of `endpoints.json`.
- `wizard.py` computes `endpoints_dir` as
  `projects/<project>/config/endpoints/<repo>/` for both `repo add` and
  `repo edit`. The `repo edit` replace branch now calls
  `shutil.rmtree(endpoints_dir)` (scoped to the current repo's dir only) before
  writing the new seed, eliminating the cross-repo glob-unlink.
- `URLSeedsHandler` and `URLOS3Handler` in `url_handlers.py` write to
  `projects/<project>/endpoints/<repo>/merged_urls.txt` and `merged_oas3.json`
  respectively.
- `purge.py` adds a second y/N prompt (full purge only) asking whether to also
  delete `endpoints/<repo>/` contents and clear `merged_seeds_path` /
  `merged_oas3_path` in `project.json`. User-provided seeds under
  `config/endpoints/` are never touched by purge.
- Stale `projects/*/config/urls/` directories and their contents were deleted
  as a one-time cleanup; affected `project.json` path keys were cleared to `""`.

---

## Alternatives Considered

### Keep the flat layout, fix the collision with unique filenames

Instead of a per-repo subdirectory, encode the repo name in the output filename
(e.g. `endpoints/<repo>_seed.json`). This avoids the directory restructure.

**Rejected because**: the `repo edit` glob-unlink bug still requires knowing
which files belong to which repo. A naming convention doesn't enforce isolation
as strongly as directory separation, and it complicates future operations that
need to clear all artifacts for one repo (e.g. repo removal). Directory
separation is the correct primitive here.

### Leave merged artifacts in `config/urls/`, add purge support there

Keep the existing output path but teach purge about `config/urls/`. No
directory rename required.

**Rejected because**: naming a derived artifact directory `config/` is
semantically wrong — it implies user-editable configuration. Placing derived
outputs under `endpoints/` (alongside tool outputs which already live in
`tool_outputs/`) keeps the distinction clear: `config/` is durable, `endpoints/`
is regenerable. Fixing the naming now costs little; fixing it later after more
code depends on the path costs more.

### Migrate existing data to the new layout automatically

Walk existing projects on startup and move files to the new per-repo paths.

**Rejected because**: the existing data was stale and incorrect (all repos in
the DVPA project pointed at the same `endpoints.json` from the last `repo add`).
Migrating corrupt data preserves the corruption. A clean slate with user
re-attachment is safer and simpler. There was only one active project at the
time the fix was applied.

---

## Pros

- Adding or editing endpoint files for two repos in the same project no longer
  overwrites each other — each repo has an isolated directory.
- `repo edit` replace now atomically wipes only the current repo's
  `config/endpoints/<repo>/` directory; other repos are structurally
  impossible to affect.
- Merged URL artifacts are clearly separated from durable config (`config/`
  vs `endpoints/`), making their regenerability explicit in the directory name.
- Purge is now complete: a full purge with "y" to the second prompt leaves no
  stale scan state anywhere on disk.
- Fixed filename `seed.json` (rather than a derived name) simplifies any future
  code that needs to reference the normalised seed by path.

---

## Cons

- Existing projects with endpoint files configured must re-attach them via
  `repo edit` — there is no migration path.
- The `merged_seeds_path` field name in `project.json` remains as-is despite
  the file now being named `merged_urls.txt` (renamed from `_seeds.txt`).
  This field-name / filename inconsistency is accepted as a minor wart to avoid
  a schema migration for all existing `project.json` files.
- A second interactive prompt during `purge` adds friction, even though most
  users will answer "n" (keep merged files).

---

## Consequences

### Positive
- Multi-repo projects can safely use per-repo endpoint files without any
  manual workaround.
- Purge is idempotent and complete — running it twice produces the same result
  with no residual stale state.
- `config/endpoints/<repo>/` can be safely backed up or version-controlled as
  part of project configuration without capturing regenerable scan artifacts.

### Negative
- Any external tooling or scripts that referenced
  `projects/<project>/endpoints/endpoints.json` or
  `projects/<project>/config/urls/<repo>_*.{txt,json}` will break silently —
  the old paths no longer exist.
- The `endpoints/` directory now holds two different kinds of content under the
  same repo subdirectory: merged OAS3 (from URL pipeline) and nothing else —
  it does not hold tool outputs (those remain in `tool_outputs/`). A new
  contributor might find the directory split between `tool_outputs/`, `endpoints/`,
  and `config/endpoints/` non-obvious.

### New Decisions Required
- If repo removal is ever added to the REPL, it will need to clean up
  `config/endpoints/<repo>/` and `endpoints/<repo>/` as part of that operation.
- The `merged_seeds_path` field name in `Repository` should eventually be
  renamed to `merged_urls_path` to match the actual filename. This was deferred
  to avoid a migration.

---

## Influences

- Bug discovered during development of the multi-repo URL crawling feature
  (TAL-111). The collision was not observable in single-repo projects, which
  explains why it was not caught earlier.
- The existing pattern in `_delete_tool_output_files` (scoped deletion of
  per-tool directories) directly informed the design of `_delete_merged_endpoints`.
- ADR-0012 established Noir → OAS3 → ZAP as the canonical discovery-to-scan
  chain; this ADR fixes the storage layer that feeds that chain in multi-repo
  projects.

---

## Related Decisions

- [ADR-0012: Noir as pre-DAST step with OAS3 file passthrough to ZAP](./ADR-0012-noir-as-pre-dast-step-with-oas3-file-passthrough-to-zap.md) — this ADR fixes the storage layer for the user-provided seed that ADR-0012 introduced
- Future ADR needed: repo removal command — must include cleanup of `config/endpoints/<repo>/` and `endpoints/<repo>/`
- Future ADR needed: rename `merged_seeds_path` to `merged_urls_path` in the `Repository` schema

---

## Review Date

Review if a repo removal command is added to the REPL — that feature must account
for this directory layout. Otherwise no calendar review needed; the layout is
stable and unlikely to change.
