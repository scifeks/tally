# Codebase Reconnaissance for Vulnerability Scanning

## Mission

Map the target codebase's attack surface to produce a structured reconnaissance
manifest. You are NOT performing vulnerability analysis. Your job is to discover
entry points, enumerate user-controlled inputs, build a shallow call graph to
dangerous sinks, map trust boundaries, partition code for parallel scanning, and
identify dead code.

The output is a single markdown file containing the attack surface map that
downstream scanner agents will consume.

---

## Step 1: Language and Framework Detection

Detect the languages, frameworks, and package managers present in the codebase.

Run globbing patterns to identify source files:

```bash
find . -type f \( -name '*.py' -o -name '*.php' -o -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' \) | grep -v node_modules | grep -v vendor | grep -v __pycache__ | head -20
```

Detect frameworks by grepping for characteristic imports:

```bash
# Python frameworks
grep -r "from flask import\|from django\|from fastapi import\|import click\|import argparse\|import typer\|from graphene import\|from ariadne import\|from strawberry import" . --include="*.py" 2>/dev/null | head -3

# PHP frameworks
grep -r "use Illuminate\\\|use Slim\\\|use Symfony\\\|use Laminas\\\\" . --include="*.php" 2>/dev/null | head -3

# JavaScript/TypeScript frameworks
grep -r "require.*express\|from.*express\|require.*koa\|from.*koa\|require.*fastify\|from.*graphql\|from.*@apollo\|from.*commander\|from.*yargs" . --include="*.js" --include="*.ts" 2>/dev/null | head -3
```

Detect package managers:

```bash
ls -la package.json requirements.txt pyproject.toml composer.json 2>/dev/null
```

Record in the output:
- Languages found (Python, PHP, JavaScript, TypeScript, or combinations)
- Frameworks detected (Flask, Django, FastAPI, Express, Laravel, Slim, Strawberry, etc.)
- Package managers present

Budget: 5-10 grep/glob calls maximum.

---

## Step 2: Entry Point Enumeration

Discover every production entry point. Use framework-specific patterns.

### HTTP Routes

**Flask:**

```bash
grep -rn "@app.route\|@blueprint.route\|add_url_rule" . --include="*.py" 2>/dev/null
```

**Django:**

```bash
grep -rn "urlpatterns\|path(\|re_path(" . --include="*.py" 2>/dev/null
```

**FastAPI:**

```bash
grep -rn "@app.get\|@app.post\|@router.get\|@router.post" . --include="*.py" 2>/dev/null
```

**Express/Koa:**

```bash
grep -rn "app.get(\|app.post(\|router.get(\|router.post(" . --include="*.js" --include="*.ts" 2>/dev/null
```

**Laravel:**

```bash
grep -rn "Route::get\|Route::post\|Route::resource" . --include="*.php" 2>/dev/null
```

**Slim:**

```bash
grep -rn "\$app->get(\|\$app->post(" . --include="*.php" 2>/dev/null
```

### CLI Handlers

```bash
# Click, argparse, typer
grep -rn "@click.command\|@click.group\|add_parser(\|add_argument(\|@app.command" . --include="*.py" 2>/dev/null

# Commander, yargs
grep -rn ".command(\|.command(" . --include="*.js" --include="*.ts" 2>/dev/null
```

### GraphQL Resolvers

```bash
grep -rn "@strawberry.type\|@strawberry.mutation\|resolve_\|typeDefs\|resolvers" . --include="*.py" --include="*.js" --include="*.ts" 2>/dev/null
```

### WebSocket, Queue, Cron, Middleware

```bash
grep -rn "@socketio.on\|ws.on(\|@celery.task\|@periodic_task\|@app.before_request\|app.use(" . --include="*.py" --include="*.js" --include="*.ts" --include="*.php" 2>/dev/null
```

For each entry point, record:
- HTTP method (GET, POST, PUT, DELETE, etc., if applicable)
- Route pattern or command name
- Handler function or method name
- File and line number

Exclude test files (`test_*.py`, `*_test.py`, `*.test.js`, `*.spec.js`, `__tests__`, `tests`, `test`),
vendored code (`vendor/`, `node_modules/`), and generated code.

---

## Step 3: Input Inventory

For each entry point discovered in Step 2, identify user-controlled inputs by
reading the handler function (1-2 reads per entry point).

Input sources:

- HTTP query parameters: `request.args`, `request.GET`, `req.query`, `$_GET`
- HTTP body: `request.json`, `request.form`, `req.body`, `$_POST`, `request.data`
- HTTP headers: `request.headers`, `req.headers`, `$_SERVER['HTTP_*']`
- HTTP cookies: `request.cookies`, `req.cookies`, `$_COOKIE`
- URL path parameters: route variables like `<id>`, `:id`, `{id}`
- File uploads: `request.files`, `req.file`, `$_FILES`
- CLI arguments: parsed args from argparse, click, typer, commander
- WebSocket message body
- Queue message payload

For each entry point, produce a row in a table:

```
| # | Source Type | Location | Variable Name | Entry Point | Trust Level |
|---|---|---|---|---|---|
| 1 | query param | /api/users | user_id | GET /api/users | unauth |
| 2 | body field | /api/upload | file_name | POST /api/upload | auth |
```

Trust level values:
- `unauth`: No authentication check before this input is consumed
- `auth`: Authentication middleware or decorator present
- `internal`: Not reachable from outside the application

Budget: 1-2 reads per entry point.

---

## Step 4: Shallow Call Graph

For each entry point handler function, map the call chain to dangerous sinks.

For each entry point:

1. Read the handler function body (1 read)
2. List every function or method defined in the codebase (not framework/library) that it calls directly
3. For each Level 1 callee, read its body and list functions it calls (Level 2)
4. Identify which functions reach dangerous sinks

Dangerous sink patterns:

- SQL execution: `.execute(`, `.query(`, `.raw(`, `cursor.`
- OS command execution: `system(`, `exec(`, `popen(`, `subprocess.`, `shell_exec(`
- File I/O: `open(`, `read(`, `write(`, `unlink(`, `file_get_contents(`
- HTTP/Network: `requests.get(`, `fetch(`, `curl(`, `http.get(`
- Template rendering: `render(`, `render_to_string(`, `Markup(`
- Deserialization: `pickle.loads(`, `unserialize(`, `json.loads(` in eval context

For each entry point, produce a row:

```
| Entry Point | Inputs | App Functions Called | Sinks Reached | Files Touched |
|---|---|---|---|---|
| GET /api/users | user_id, role | get_user() -> fetch_profile() | SQL execute | models/user.py, services/auth.py |
```

Budget: 2-4 reads per entry point total. Do NOT trace deep data flow paths; that
is the scanner's job. Stop at Level 2.

---

## Step 5: Trust Boundary Map

Identify authentication boundaries and external system calls.

### Auth Boundaries

Grep for authentication middleware and decorators:

```bash
grep -rn "@login_required\|@requires_auth\|IsAuthenticated\|authMiddleware\|auth:" . --include="*.py" --include="*.js" --include="*.ts" --include="*.php" 2>/dev/null
```

For each entry point, note whether it is protected by an auth check or not.

### External System Calls

From the call graph (Step 4), identify where data flows to:
- Databases (SQL, NoSQL, ORM calls)
- External APIs (HTTP/HTTPS calls to third-party services)
- File system (file read/write operations)
- Subprocesses (command execution)
- Message queues (Celery, RabbitMQ, SQS, etc.)

### Third-Party Integrations

List external services the codebase integrates with:
- Payment processors (Stripe, PayPal, etc.)
- Email services (SendGrid, AWS SES, etc.)
- Cloud storage (AWS S3, GCP Cloud Storage, etc.)
- Analytics (Segment, Mixpanel, etc.)
- Chat/messaging (Slack, Discord, Twilio, etc.)

Output as a narrative list with file:line references:

```
- Auth boundary at middleware/auth.py:15 (protects routes under /api/protected)
- Database writes to PostgreSQL via ORM in services/user.py
- External HTTP call to Stripe API in payment/processor.py:42
- File uploads stored to /var/uploads via handlers/upload.py:18
```

---

## Step 6: Shared Infrastructure Catalog

Identify modules imported by more than 50% of entry point handler chains.
These are shared infrastructure and should NOT define partition boundaries.

Method:
1. For each app-defined module in the call graph, count how many entry point chains import it
2. If import count > 50% of total entry points, add to shared infrastructure

Examples:
- Logger modules imported by all endpoints
- ORM models imported by most data handlers
- Auth utility modules imported by protected endpoints
- Configuration modules imported everywhere

Output as a table:

```
| Module | Role | Files | Entry Points Using | Percentage |
|---|---|---|---|---|
| application.auth | Authentication | auth.py, decorators.py | 18 | 72% |
| domain.models | Data models | models.py | 22 | 88% |
```

---

## Step 7: Partition Computation

Compute scope partitions for parallel scanning using union-find.

1. Start with each entry point in its own set
2. For each app-specific function in the call graph (NOT in shared infrastructure),
   find all entry points that call it
3. Merge those entry points' sets
4. Each result is a partition (labeled SG-1, SG-2, etc.)

Handle pathological cases:

- Partition with >20 inputs or >15 files: sub-partition by route prefix or file
- Single function connecting everything: promote to shared infrastructure and
  recompute
- Cannot split below 20 inputs: mark `SEQUENTIAL-FALLBACK`
- Partition with <=2 inputs and 1 file: merge with nearest partition

Output as a table:

```
| Partition | Input Count | Entry Points | App-Specific Files | Shared Nodes | Status |
|---|---|---|---|---|---|
| SG-1 | 8 | GET /users, GET /users/:id, POST /users | services/user.py, models/user.py | auth, logging | parallel |
| SG-2 | 5 | POST /upload, GET /file/:id | handlers/upload.py | auth, storage | parallel |
| SG-3 | 18 | (all admin routes) | admin/*.py | auth, logging, models | SEQUENTIAL-FALLBACK |
```

---

## Step 8: Dead Code Inventory

Identify unreachable code by comparing all source files against partition
membership.

1. List all production source files (Python, PHP, JavaScript, TypeScript) excluding tests, vendor, generated
2. List all files appearing in any partition's "App-Specific Files"
3. The difference is the dead code inventory

For each dead code file, determine:
- Whether it contains dangerous sinks from Step 4
- Whether it defines unused functions or classes (check for imports)
- Whether it appears abandoned, legacy, or a failed feature

Output as a table:

```
| File | Contains Sinks | Unused Symbols | Notes |
|---|---|---|---|
| legacy/old_payment.py | yes | process_payment, validate_card | Appears abandoned; newer payment logic in payment/processor.py |
| utils/deprecated_auth.py | no | login_user, logout_user | Unused utilities; production uses auth.py |
```

---

## Output Format

Write a single markdown file with these H2 sections in the order listed:

1. `## Codebase Profile` (languages, frameworks, package managers, file counts)
2. `## Entry Points` (count and brief summary)
3. `## Input Inventory` (numbered table with >5 example rows)
4. `## Trust Boundary Map` (auth boundaries, external calls, integrations)
5. `## Application Call Graph` (entry point to sinks table)
6. `## Shared Infrastructure` (table)
7. `## Scope Partitions` (table with partition allocation)
8. `## Dead Code Inventory` (table with dangerous sink callouts)

Use H1 for the document title. Use H3 for subsections within major sections if
needed. Use fenced code blocks with language hints for grep patterns. Use
markdown tables for all structured output.

---

## Constraints

- Return message must be under 20 words (the manifest file itself IS the output)
- Do NOT perform vulnerability analysis; only map the attack surface
- Exclude test files, vendored code, generated code, build artifacts
- If no detectable entry points (pure library): report that explicitly and
  produce an empty partition table
- Budget: aim for 50-80 total grep/read calls for entire recon; be efficient
- Follow LANGUAGE.md rules:
  - No em dashes; restructure sentences instead
  - American English spelling (color, analyze, initialize, behavior)
  - No emoji or decorative unicode
  - Terse and direct prose
  - Line length: 88 characters maximum

---

## Success Criteria

The manifest is complete when:
- All entry points in the codebase are enumerated
- All user-controlled inputs for each entry point are identified
- Call chains from entry points to dangerous sinks are mapped
- Trust boundaries (auth, data flow) are documented
- Partitions are feasible for parallel scanning (no partition >20 inputs or >15
  files without SEQUENTIAL-FALLBACK marker)
- Dead code inventory accounts for all non-partition files
- Every table and structured section matches the format shown above
