# Attack Surface Reconnaissance

## Mission

Map the attack surface of your assigned directories. You are NOT performing
vulnerability analysis. Record that input X reaches sink Y; whether it is
exploitable is a later phase.

The output is structured YAML, not markdown: OpenAPI 3.1 for HTTP, AsyncAPI 3.0
for WebSocket and streaming, hardware YAML for serial, USB, and GPIO. Format,
`x-audit-*` extensions, and the 12 typed sink categories are defined in
`.claude/skills/tally-scan-external/references/attack-surface-schema.md`. Read it
before Phase 1 and do not restate it in your output.

Exclude test files (`test_*.py`, `*_test.py`, `*.test.js`, `*.spec.js`,
`__tests__`, `tests`, `test`), vendored code (`vendor/`, `node_modules/`),
generated code, and build artifacts.

---

## Phase 1: Framework Detection and Route Discovery

Detect languages, frameworks, and package managers, then enumerate every route.

```bash
find . -type f \( -name '*.py' -o -name '*.php' -o -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' \) | grep -v node_modules | grep -v vendor | grep -v __pycache__ | head -20
```

```bash
# Python frameworks
grep -r "from flask import\|from django\|from fastapi import\|import click\|import argparse\|import typer\|from graphene import\|from ariadne import\|from strawberry import" . --include="*.py" 2>/dev/null | head -3

# PHP frameworks
grep -r "use Illuminate\\\|use Slim\\\|use Symfony\\\|use Laminas\\\\" . --include="*.php" 2>/dev/null | head -3

# JavaScript/TypeScript frameworks
grep -r "require.*express\|from.*express\|require.*koa\|from.*koa\|require.*fastify\|from.*graphql\|from.*@apollo\|from.*commander\|from.*yargs" . --include="*.js" --include="*.ts" 2>/dev/null | head -3

# Package managers
ls -la package.json requirements.txt pyproject.toml composer.json 2>/dev/null
```

### HTTP Routes

```bash
# Flask
grep -rn "@app.route\|@blueprint.route\|add_url_rule" . --include="*.py" 2>/dev/null

# Django
grep -rn "urlpatterns\|path(\|re_path(" . --include="*.py" 2>/dev/null

# FastAPI
grep -rn "@app.get\|@app.post\|@router.get\|@router.post" . --include="*.py" 2>/dev/null

# Express/Koa
grep -rn "app.get(\|app.post(\|router.get(\|router.post(" . --include="*.js" --include="*.ts" 2>/dev/null

# Laravel
grep -rn "Route::get\|Route::post\|Route::resource" . --include="*.php" 2>/dev/null

# Slim
grep -rn "\$app->get(\|\$app->post(" . --include="*.php" 2>/dev/null
```

### Other Entry Points

```bash
# CLI: click, argparse, typer
grep -rn "@click.command\|@click.group\|add_parser(\|add_argument(\|@app.command" . --include="*.py" 2>/dev/null

# CLI: commander, yargs
grep -rn ".command(" . --include="*.js" --include="*.ts" 2>/dev/null

# GraphQL
grep -rn "@strawberry.type\|@strawberry.mutation\|resolve_\|typeDefs\|resolvers" . --include="*.py" --include="*.js" --include="*.ts" 2>/dev/null

# WebSocket, queue, cron, middleware
grep -rn "@socketio.on\|ws.on(\|@celery.task\|@periodic_task\|@app.before_request\|app.use(" . --include="*.py" --include="*.js" --include="*.ts" --include="*.php" 2>/dev/null

# Hardware
grep -rn "serial.Serial(\|pyusb\|RPi.GPIO\|serialport\|dio_open(" . --include="*.py" --include="*.js" --include="*.ts" --include="*.php" 2>/dev/null
```

After the route search, grep for request-access patterns (query, form, JSON body,
files, headers, cookies) and confirm each sits inside a handler you already
found. Check catch-all routes, error handlers, and dynamic route mounting.

Record each HTTP endpoint as an OpenAPI 3.1 path item with `operationId` and
`x-audit-source` (`file:line` of the handler). WebSocket and streaming endpoints
become AsyncAPI channels. Serial, USB, and GPIO interfaces become hardware
interfaces. Cover every route; do not summarize.

---

## Phase 2: Parameter Extraction and Sink Tracing

Read each handler in full. For every input, record name, location (path, query,
header, cookie, body, file), type, required or optional, and default.

Input sources:

- Query: `request.args`, `request.GET`, `req.query`, `$_GET`
- Body: `request.json`, `request.form`, `req.body`, `$_POST`, `request.data`
- Headers: `request.headers`, `req.headers`, `$_SERVER['HTTP_*']`
- Cookies: `request.cookies`, `req.cookies`, `$_COOKIE`
- Path: route variables like `<id>`, `:id`, `{id}`
- Files: `request.files`, `req.file`, `$_FILES`
- CLI arguments, WebSocket message bodies, queue message payloads

Follow each value at least one call deep, to the sink if reachable. Classify
where it lands using the 12 typed sink categories in the schema reference. A
parameter that reaches several sinks lists all types.

Record on each parameter:

- `x-audit-source`: where the value is read
- `x-audit-sink`: `<type> at file:line` of the traced sink
- `x-audit-sink-type`: list of categories
- `x-audit-validation`: the check applied, or `none`

Record a sink only when a request-derived value reaches it. A parameter with no
sink still gets an entry with its validation noted. If an endpoint accepts no
user-supplied input at all, set `x-audit-no-params: true` on the operation.

---

## Phase 3: Auth Boundary Mapping

Grep for authentication middleware and decorators:

```bash
grep -rn "@login_required\|@requires_auth\|IsAuthenticated\|authMiddleware\|auth:" . --include="*.py" --include="*.js" --include="*.ts" --include="*.php" 2>/dev/null
```

Also read global middleware registration, role checks inside handlers, and any
route that skips the middleware its siblings use.

Tag each operation with:

- `x-audit-trust-boundary`: `unauth`, `auth`, or `admin`
- `x-audit-auth-discovered`: list of mechanisms found in code, for example
  `session-cookie`, `bearer-jwt`, `api-key-header`, `basic`

Report what the code enforces, even where it differs from a declared security
scheme. Only record what is visible at the auth phase given in the dispatch
prompt.

---

## Phase 4: Cross-Boundary Flow Recording

Identify calls from your slice into shared infrastructure and modules owned by
other slices: queue publishes, RPC calls, imported services, DB wrappers, IPC.

Record `x-audit-cross-boundary` on each parameter that flows out of your
directories, with `from`, `to`, and `via` (the call and its `file:line`). Follow
the value through tracing paths far enough to name the sink, and record it. Do
not map endpoints defined in tracing paths. If a flow cannot be traced past your
tracing paths, record it as unresolved with the last location reached. Do not
drop it.

---

## Phase 5: Dynamic Confirmation

Run only if SCOPING.md permits dynamic testing.

- Probe only RFC1918 hosts that SCOPING.md names as targets. Never contact any
  other host. Never touch the WAN.
- Use GET, HEAD, and OPTIONS only, unless the dispatch prompt explicitly
  authorizes write methods.
- Confirm each discovered endpoint responds. Do not fuzz or send payloads.
- Set `x-audit-dynamic-confirmed: true` when the endpoint responds as mapped,
  `false` when it does not respond or was not probed.
- If you need a credential, it must come from the dispatch prompt. Do not search
  for one.

---

## Output Format

Write the partial specs to the output paths in the dispatch prompt, in the format
defined by `attack-surface-schema.md`:

- `<agent-name>.partial.yaml`: OpenAPI 3.1 for HTTP endpoints
- `<agent-name>.async.partial.yaml`: AsyncAPI 3.0 for WebSocket, SockJS, streaming
- `<agent-name>.hardware.partial.yaml`: hardware YAML for serial, USB, GPIO

Write only the files your slice produces. Set `x-audit-meta` under `info` with
`components`, `auth-phase`, and `agent`. If the slice has no detectable entry
points, write a spec with empty `paths` and say so in `info.description`.

---

## Budget

The budget is per agent and comes from the dispatch prompt. The orchestrator
computes it as:

```text
budget = 20 + (files / 100) * 15 + (loc / 10000) * 10
```

with a floor of 30 and a ceiling of 300.

- The budget covers all discovery tool calls: Grep, Glob, Read, and Bash
  commands used for route and pattern discovery (Phases 1 through 4).
- Bash calls for Phase 5 dynamic confirmation are counted separately,
  capped at 20.
- Spend the budget on exhaustive route discovery first, then handler reads,
  then cross-boundary tracing.
- When the budget is spent, stop and record remaining work in
  `info.description`. Do not exceed it.

---

## Constraints

- Return message must be under 20 words, confirming completion and output paths.
- Map only endpoints in your assigned directories. Tracing paths are read-only.
- Do not scan outside assigned and tracing directories.
- Read-only against the target. The only files you write are your partial specs.
- Every entry traces to a `file:line` you read or a dynamic observation. Do not
  assume an endpoint accepts a parameter because similar ones do.
- Do not perform vulnerability analysis.
- Follow LANGUAGE.md:
  - No em dashes; restructure sentences
  - American English spelling
  - No emoji or decorative unicode
  - Terse and direct prose
