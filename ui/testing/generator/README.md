# UI fixture generator

Generates UI test fixtures in `ui/testing/fixtures/` from real scan
data in `projects/DVPA/sqlite/findings.db` plus hand-authored seed
files for the dimensions the real DB does not cover.

## Run

```bash
cd /llm/code/tally
python ui/testing/generator/generate.py
python ui/testing/generator/check_coverage.py
```

The script is read-only with respect to all SQLite databases and the
project JSON. It writes only to `ui/testing/fixtures/`.

## Layout

- `generate.py` — orchestrator. Builds a single context dict from
  `tally.db` + `projects/DVPA/sqlite/findings.db` (per-repo config
  hydrates from the SQLite `repositories` table) plus
  `projects/DVPA/config/project.json` for project-level metadata
  (`company_name`, `department_name`, `abbreviation`), then runs
  domain producers.
- `seeds/` — hand-authored data the DB lacks. Two flavors:
  - **DB-row shape** (for findings the DB doesn't have — dalfox,
    xsstrike — and synthetic extra scan runs). These run through the
    same production serializers as real rows.
  - **Wire-shape templates** (for chat / reports / triage / config
    domains that have no DB representation). Loaded as JSON and
    placeholder ids substituted with real values from the context.

## Schema-change resilience

Every fixture is validated against the matching Pydantic response
model in `web/api/schemas.py` before write. A serializer change or
schema rename surfaces immediately as a validation error from the
generator. Seeds are stored at the input layer (DB-row shape, not
wire-shape) wherever possible so they pick up serializer changes
automatically.
