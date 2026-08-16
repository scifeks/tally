---
name: tally-scan-injection-nosql
description: >
  Scan the target repo for NoSQL injection defects. Detects operator
  injection patterns where user-controlled data reaches query operators
  as objects, and $where injection where user input reaches JavaScript
  evaluation contexts. Emits findings shaped for Tally MCP submission
  (rule_id `injection.nosql`, CWE-943, severity high). Invoke when the
  user says "NoSQL injection", "NoSQLi", "MongoDB injection", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: NoSQL injection

Detects sinks where user-controlled data reaches a NoSQL interpreter
without proper validation or sanitization. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `injection.nosql` |
| Primary CWE | `CWE-943` |
| Secondary CWE | `CWE-74` |
| OWASP 2025 category | `Injection` |
| Default severity | `high` |
| Parent label (dedup) | `NoSQLInjection` |


## Detection matrix

### Python

- **Operator injection via parsed JSON**: `collection.find(
  {"user": json.loads(user_input)})` or similar where request data is
  parsed as JSON/dict and passed directly as query operators. Attacker
  can inject `{"$gt": ""}` to change query semantics.
- **Operator injection via request body**: `collection.find(req.json())`
  or `collection.insert_one(body)` where the entire request body
  becomes a query filter or document, allowing operator injection.
- **$where injection**: `collection.find({"$where": f"this.x == 
  '{user_input}'"})` where user input reaches JavaScript evaluation.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Operator injection via json_decode**: `$collection->find([
  "user" => json_decode($userInput)])` where decoded user data becomes
  query operators.
- **Operator injection via array merge**: `$filter = array_merge(
  $baseFilter, $userData)` passed to `find()` where user data can inject
  operators.
- **$where injection**: `$collection->find(["$where" => 
  "this.x == '$userInput'"])` where user input reaches JavaScript eval.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Operator injection from request body**: `collection.find(req.body)`
  or `collection.find({user: req.body.user})` where parsed JSON from
  request body becomes query operators. Attacker sends `{"user": 
  {"$gt": ""}}`.
- **Operator injection via Object.assign**: `collection.find(
  Object.assign({}, filters, req.query))` where user-controlled query
  params can inject operators.
- **$where injection**: `collection.find({$where: 'this.x == "' + 
  userInput + '"'})` where user input reaches JavaScript code.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **Mongoose query with operator injection**: `Model.find(
  req.body.filter)` where the entire request body becomes a Mongoose
  query, allowing operator injection.
- **Direct MongoDB driver with operators**: `collection.find(
  userQuery)` where `userQuery` is user-controlled JSON converted to an
  object.
- **$where injection**: same patterns as JavaScript; TypeScript provides
  no additional safety at runtime.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a NoSQL
  injection at this location.
- When the taint source is in the same file: `meta.taint_source` naming
  the request parameter or upstream variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler to the
  sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is clearly
  variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not obviously
  user-controlled.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`injection.nosql`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what an
    attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-943", "CWE-74"],
  "finding_type": ["vulnerability"],
  "rule_id": "injection.nosql",
  "meta": {
    "title": "<short human title, e.g. 'NoSQL operator injection via
      request body'>",
    "owasp_name": "Injection",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when
      traceable>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library observed in
the code. Examples of good remediation strings:

- **pymongo (Python)**: `Extract scalar values from user input before
  passing to query methods. Instead of
  collection.find(json.loads(user_input)), construct the query
  explicitly: collection.find({"user_id": int(user_id)}).`
- **MongoDB driver (JavaScript)**: `Never pass req.body directly to
  collection.find(). Build the query from explicitly named fields:
  collection.find({user_id: req.body.id}). Validate and cast the value
  (parseInt for IDs, String for names).`
- **Mongoose (TypeScript)**: `Use Mongoose's schema validation and
  build queries from typed properties: Model.find({userId: 
  req.body.id}). For dynamic filters, use a whitelist of allowed fields
  and apply schema validation before querying.`
- **mongo-sanitize**: `Apply mongo-sanitize to strip $ and . prefixes:
  const sanitized = mongoSanitize(req.body); collection.find(sanitized).`
- **Dynamic $where**: `Never use $where with user input. Use query
  operators instead: collection.find({status: "active"}) instead of
  collection.find({$where: "this.status == '" + status + "'"}).`

Keep it two to four sentences. Vague guidance ("sanitize the input") is
worse than no guidance.

## Common false positives

- **Scalar values from validated input**: `collection.find({user_id:
  userId})` where `userId` is an integer from a trusted route parameter
  or a validated schema is safe.
- **ORM/query-builder patterns**: Mongoose model operations with schema
  validation (`Model.find({email: userEmail})`) are safe if the schema
  enforces type constraints and the code does not bypass them.
- **Static queries with no user data**: `collection.find({status:
  "active"})` is safe regardless of the driver or whether the query
  appears in a user-facing endpoint.
- **Allowlist-protected operators**: If the code validates a requested
  sort field against an allowlist before using it as a query key, the
  pattern is safe (e.g., checking `sortBy` against `["name", "date"]`).
- **Constants and enums**: operator keys or values sourced from
  application constants with no user reachability are safe.

## References

- `references/python.md`: Python patterns for pymongo, motor.
- `references/php.md`: PHP patterns for ext-mongodb, Doctrine ODM.
- `references/javascript.md`: Node patterns for mongodb (native driver),
  mongoose.
- `references/typescript.md`: TypeScript patterns for mongoose, mongodb
  driver.
