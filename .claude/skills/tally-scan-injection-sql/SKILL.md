---
name: tally-scan-injection-sql
description: >
  Scan the target repo for SQL injection defects. Detects
  string-formatted queries, unparameterized ORM raw calls, dynamic
  table/column names sourced from user input, and `execute` calls
  with f-strings or `%`-formatting. Emits findings shaped for
  Tally MCP submission (rule_id `injection.sql`, CWE-89, severity
  critical). Invoke when the user says "SQL injection", "SQLi",
  "check for SQL injection", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: SQL injection

Detects sinks where user-controlled data reaches a SQL interpreter
without parameterization. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally
through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.sql` |
| Primary CWE | `CWE-89` |
| OWASP 2025 category | `Injection` |
| Default severity | `critical` |
| Parent label (dedup) | `SQLi` |


## Detection matrix

### Python

- **String-formatted query**: an f-string, `.format()`, or
  `%`-formatting that interpolates a request-derived value into a
  SQL string, then passes the string to `execute`, `executescript`,
  `execute_many`, `read_sql`, or an equivalent driver method.
- **Concatenated query**: `+`-concatenation of a SQL literal with
  a request-derived value passed to any DB driver.
- **Unparameterized raw ORM**: `session.execute(text(<f-string>))`,
  `Model.objects.raw(<f-string>)`, `connection.cursor().execute(
  <f-string>)`. The safe form takes bind parameters as a second
  argument.
- **Dynamic identifier**: table or column name sourced from
  request data reaching `execute` (parameter placeholders do not
  cover identifiers; the safe form is an allowlist).
- **`pandas.read_sql`** with a formatted query string.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **PDO concatenation**: `$pdo->query("SELECT ... WHERE id = $id")`
  where `$id` is request-sourced. Safe form uses `prepare` and
  `execute([$id])`.
- **`mysqli_query` concatenation**: interpolation into the SQL
  argument. Safe form uses `mysqli_prepare` + `bind_param`.
- **Laravel raw**: `DB::raw()`, `DB::select("... $var ...")`,
  `->whereRaw('col = ' . $var)`, `->orderByRaw($var)`. Safe form
  passes bindings as the second argument.
- **Eloquent whereRaw with concatenation**. Safe form uses
  `->whereRaw('col = ?', [$var])`.
- **WordPress**: `$wpdb->query("SELECT ... $var")`. Safe form is
  `$wpdb->prepare(...)`.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **`pg` concatenation**: `client.query('SELECT ... ' + userId)`.
  Safe form uses positional parameters:
  `client.query('SELECT ... WHERE id = $1', [userId])`.
- **`mysql`/`mysql2` concatenation**: template literal or `+` into
  the SQL string. Safe form uses `?` placeholders and a bind
  array.
- **Knex `.raw()` with interpolation**. Safe form uses parameter
  bindings: `knex.raw('... = ?', [userId])`.
- **Sequelize `query()` with string interpolation**. Safe form
  passes `replacements` or `bind` options.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

- **Prisma `$queryRaw`**: safe when used as a tagged template
  (`prisma.$queryRaw`SELECT ... WHERE id = ${userId}``), unsafe
  when used as a regular function (`prisma.$queryRawUnsafe`).
- **TypeORM `query()`**: string interpolation into the SQL
  argument. Safe form uses parameter bindings.
- **Sequelize `Sequelize.literal()`** with request data.
- Same JavaScript sinks apply on the Node runtime.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  SQLi at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler
  to the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.sql`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an attacker can do>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-89"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.sql",
  "meta": {
    "title": "<short human title, e.g. 'SQL injection via f-string in login handler'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation
strings:

- **sqlite3 (Python)**: `Use ? placeholders and pass the values as
  a tuple: cursor.execute('SELECT * FROM users WHERE id = ?',
  (user_id,)). sqlite3 does not support named placeholders in the
  ? style; use :name if you need named binds.`
- **psycopg2 (Python)**: `Use %s placeholders (not %d, not %r) and
  pass a tuple: cursor.execute('SELECT * FROM users WHERE id = %s',
  (user_id,)). psycopg2 handles quoting; do not pre-quote.`
- **PDO (PHP)**: `Use prepared statements: $stmt = $pdo->prepare(
  'SELECT * FROM users WHERE id = ?'); $stmt->execute([$id]);.
  Never concatenate user input into the SQL string.`
- **Laravel Eloquent**: `Use the query builder's parameter binding:
  Model::where('id', $id)->first(). If a raw fragment is truly
  needed, pass bindings: ->whereRaw('col = ?', [$value]).`
- **Prisma**: `Use the typed query builder: prisma.user.findFirst(
  {where: {id: userId}}). Only reach for $queryRaw when the shape
  is not expressible; when doing so, use the tagged-template form
  ($queryRaw, not $queryRawUnsafe).`
- **Dynamic identifier**: `SQL parameter placeholders do not cover
  table or column names. Validate the identifier against an
  explicit allowlist before splicing it into the query, and reject
  anything that does not match.`

Keep it two to four sentences. Vague guidance ("parameterize the
query") is worse than no guidance.

## Common false positives

- **Static-string queries with no interpolation**: `execute(
  'SELECT id FROM users WHERE active = 1')` is safe regardless of
  the driver.
- **Parameter-list bindings**: `execute(sql, params)` where `sql`
  is a literal string and `params` is a tuple/list is safe. The
  presence of `%s` in the string is a placeholder, not
  interpolation.
- **ORM query builders with typed fields**:
  `User.objects.filter(id=user_id)`, `Model::where('id', $id)`,
  `prisma.user.findFirst({where: {id: userId}})` are safe by
  design.
- **Constants and enums**: interpolation of module-level constants
  or enum values with no user reachability is safe. Confirm the
  value is not later reassigned from a request.

## References

- `references/python.md`: Python patterns for sqlite3, psycopg2,
  asyncpg, SQLAlchemy, Django ORM, pandas.
- `references/php.md`: PHP patterns for PDO, mysqli, Laravel
  Eloquent, WordPress `$wpdb`.
- `references/javascript.md`: Node patterns for `pg`, `mysql2`,
  Knex, Sequelize.
- `references/typescript.md`: TypeScript patterns for Prisma,
  TypeORM, Sequelize.
