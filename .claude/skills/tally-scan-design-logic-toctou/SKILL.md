---
name: tally-scan-design-logic-toctou
description: >
  Scan the target repo for TOCTOU (time-of-check to time-of-use) race
  conditions. Detects check-then-act patterns on shared state where a
  concurrent thread or process can alter the state between the check and
  the use. Emits findings shaped for Tally MCP submission (rule_id
  `design_logic.toctou`, CWE-367, CWE-362, severity high). Invoke when
  the user says "TOCTOU", "race condition", "time-of-check time-of-use",
  "check then act", or when dispatched by `tally-scan-external`.
---

# Tally scanner: TOCTOU race conditions

Detects time-of-check to time-of-use vulnerabilities where code checks a
condition on shared state, then acts on the assumption the state has not
changed. An attacker or concurrent request can modify the state between
the check and the use, leading to security bypass or data corruption.
Runs per-file in the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill directly).
Emits a JSON list of findings; the orchestrator or the user submits them to
Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `design_logic.toctou` |
| Primary CWE | `CWE-367` |
| Secondary CWE | `CWE-362` |
| OWASP 2025 category | `Insecure Design` |
| Default severity | `high` |
| Parent label (dedup) | `TOCTOU` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 10.

## Detection matrix

### Python

- **File existence check then open**: `os.path.exists(path)` or
  `os.path.isfile(path)` followed by `open(path)`. Between check and
  open, a symlink attack can replace the file with a symlink pointing to
  a sensitive file.
- **File permission check then read/write**: `os.access(path, os.W_OK)`
  followed by `open(path, 'w')` or `open(path, 'r')`. Permissions can
  change between check and open, or the file can be replaced.
- **Directory existence check then create**: `if not
  os.path.exists(path): os.makedirs(path)`. Another process can create
  the directory after the check, causing `makedirs` to fail or create
  unexpected nesting.
- **Balance/quota check then debit**: `if user.balance >= amount:
  user.balance -= amount` without database atomicity. Another request can
  debit the same balance before the first update completes.
- **Unique constraint check then insert**: `if not
  Model.objects.filter(email=email).exists(): Model.objects.create(
  email=email)`. Another request can insert the same email after the
  check, violating uniqueness.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **File existence check then read/include**: `file_exists($path)`
  followed by `file_get_contents($path)` or `include($path)`. A symlink
  can be planted between check and read, redirecting to a sensitive file.
- **Permission check then write**: `is_writable($dir)` followed by
  `file_put_contents($dir . '/' . $name, $data)`. Permissions or directory
  contents can change between check and write.
- **Database unique check then insert**: `if (!$db->query("SELECT ...
  WHERE email = '$email'")->fetch()) { $db->query("INSERT ..."); }`.
  Another request can insert the same email after the check.
- **File locking missing**: File operations in concurrent request handlers
  without `flock()` between existence check and file operations, leaving a
  window for another request to interfere.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **File existence check then read**: `fs.existsSync(path)` followed by
  `fs.readFileSync(path)` or async `fs.access()` followed by
  `fs.readFile()`. The file can be deleted, replaced, or symlinked between
  check and read.
- **File permission check then access**: `fs.statSync(path)` to check
  permissions followed by `fs.readFileSync(path)` or `fs.writeFileSync(
  path)`. Permissions can change, or the file can be replaced.
- **Database find-then-insert without atomicity**: `findOne()` followed by
  `create()` in Mongoose or Sequelize, without `upsert` or a transaction.
  Another request can insert the same record after the find, violating
  uniqueness or business logic.
- **Redis GET then SET without atomicity**: `client.GET(key)` followed by
  `client.SET(key, value)` without using `SETNX` (set if not exists) or a
  Lua script. Another client can modify the key between GET and SET.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Prisma findFirst then create without upsert**: `await
  prisma.model.findFirst({where: {...}})` followed by `await
  prisma.model.create(...)` without wrapping in `upsert()` or a
  `$transaction()`. Another request can create the same record after the
  find.
- **TypeORM findOneBy then save without transaction**: `await
  repo.findOneBy({email})` followed by `await repo.save(entity)` without
  `@Transaction()` or a query runner transaction. Another request can
  insert the same entity after the find.
- **fs (typed) with same patterns as JavaScript**: The TypeScript type
  wrappers do not change the underlying TOCTOU vulnerability in Node's fs
  module.
- **Database operation split across async boundaries**: An `await` between
  a check and an act in an async handler, during which another request can
  run and change the shared state.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the check or act line (the first
  observable manifestation).
- `meta.code_snippet`: 3-8 lines of source showing the check and the
  subsequent act.
- `meta.reasoning`: one sentence explaining the TOCTOU window and why it
  is exploitable at this location.
- `meta.shared_resource`: the resource being checked then used (file path,
  database row, balance field, cache key).

Set `confidence`:

- `confirmed` when the check and act are in the same function and the race
  window is obvious.
- `probable` when the check and act are separated by an async/IO boundary,
  or the act is called by a helper function.
- `potential` when the check and act may not be in the same execution path
  or the shared resource is inferred.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`design_logic.toctou`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose: check-act pattern, race window, security impact>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-367", "CWE-362"],
  "finding_type": ["vulnerability"],
  "rule_id": "design_logic.toctou",
  "meta": {
    "title": "<short title, e.g. 'TOCTOU via file check and open'>",
    "owasp_name": "Insecure Design",
    "remediation": "<per-finding, per D19; see remediation guidance>",
    "code_snippet": "<3-8 lines of source showing check and act>",
    "shared_resource": "<file path, database row, cache key, balance>",
    "reasoning": "<one sentence explaining TOCTOU window>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library or
pattern observed in the code. Examples of good remediation strings:

- **Python file operations (tempfile)**: `Use tempfile.mkstemp() or
  NamedTemporaryFile to create and open a file atomically. mkstemp()
  returns a file descriptor opened for exclusive use, eliminating the race
  window between creation and open.`
- **Python file operations (open with 'x')**: `Use open(path, 'x') with
  exclusive-creation mode, which raises FileExistsError if the file
  exists. This is atomic; no race window.`
- **Python database uniqueness**: `Use Model.objects.get_or_create() or
  update_or_create() instead of exists() + create(). These use INSERT ...
  ON CONFLICT internally and are atomic.`
- **PHP file operations (fopen)**: `Use fopen($path, 'x') for exclusive
  creation mode. For concurrent writes, acquire flock($handle, LOCK_EX)
  immediately after opening and hold it until the write is complete.`
- **PHP database uniqueness**: `Wrap the check-and-insert in a database
  transaction with BEGIN, then SELECT ... FOR UPDATE to lock the rows.
  Or use INSERT ... ON DUPLICATE KEY UPDATE to make the operation atomic.`
- **JavaScript fs operations**: `Use fs.open(path, 'wx') with exclusive
  creation flag, or for async, use fs.promises.open(path, 'wx'). This
  fails atomically if the file exists, closing the race window.`
- **Prisma database uniqueness**: `Use prisma.model.upsert() instead of
  findFirst() + create(). For multi-step operations, wrap in
  prisma.$transaction() to ensure atomicity.`
- **Balance/quota atomicity**: `Use an atomic database update: UPDATE
  accounts SET balance = balance - :amount WHERE id = :id AND balance >=
  :amount. Check the affected row count to determine success; if zero
  rows were affected, the balance was insufficient.`

Keep it two to four sentences. Reference the specific API or SQL pattern.

## Common false positives

- **File operations on read-only filesystem paths**: Bundled assets or
  config files loaded once at startup with no concurrent writes are safe,
  even with check-then-use patterns.
- **Existence checks for UI feedback or logging**: Checking if a file
  exists to populate a debug log or UI field, then separately using the
  file with its own open-time error handling, is generally safe. The
  exploit window must reach a security-relevant decision.
- **Single-threaded CLI tools**: Check-then-act in a command-line tool
  with no concurrency is safe; no other process can interfere during
  execution.
- **Database operations inside an outer transaction with appropriate
  isolation**: If the entire check-and-act sequence is inside a
  transaction at SERIALIZABLE or REPEATABLE READ isolation, the TOCTOU
  window is closed by the database engine.
- **File operations inside flock/advisory lock scope**: If the check and
  act are both protected by flock() or an advisory lock, the race is
  closed.
- **os.makedirs(path, exist_ok=True)** (Python): This is atomic; the
  exist_ok flag tells makedirs to succeed even if the directory already
  exists. No TOCTOU.
- **Prisma upsert or $transaction**: If the find-and-create is replaced
  with upsert() or wrapped in $transaction(), the race is closed.

## References

- `references/python.md`: Python patterns for os/pathlib, tempfile, Django
  ORM, SQLAlchemy transactions.
- `references/php.md`: PHP patterns for file operations, flock, PDO
  transactions, Laravel.
- `references/javascript.md`: Node patterns for fs/fs.promises, Mongoose
  upsert, Sequelize transactions, Redis.
- `references/typescript.md`: TypeScript patterns for Prisma, TypeORM,
  fs (typed), async transactions.
