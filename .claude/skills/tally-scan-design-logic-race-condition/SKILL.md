---
name: tally-scan-design-logic-race-condition
description: >
  Scan the target repo for race condition vulnerabilities (CWE-362) beyond
  TOCTOU. Detects concurrent operations on shared state that can lead to
  security issues: asyncio mutations without locks, thread-unsafe shared
  state, concurrent database writes without transactions, file operations
  without flock, session data races. Emits findings shaped for Tally MCP
  submission (rule_id `design_logic.race_condition`, CWE-362, severity
  high). Invoke when the user says "race condition", "concurrent", "thread
  safety", "mutex", or when dispatched by `tally-scan-external`.
---

# Tally scanner: race condition vulnerabilities

Detects race conditions where concurrent operations on shared state can lead
to security issues. Unlike TOCTOU (check-then-act), race conditions broadly
cover any unguarded concurrent access to shared resources: asyncio shared
state mutations without locks, database operations without transactions,
file operations without file locking, session data races in request handlers,
and similar patterns. An attacker or concurrent request can modify the state
during the vulnerable window, leading to security bypass, data corruption,
or information disclosure. Runs per-file in the target repo (as dispatched
by the `tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the orchestrator
or the user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `design_logic.race_condition` |
| Primary CWE | `CWE-362` |
| OWASP 2025 category | `Insecure Design` |
| Default severity | `high` |
| Parent label (dedup) | `Race Condition` |


## Detection matrix

### Python

- **asyncio shared state mutation without lock**: `asyncio` application
  modifies shared variables or data structures from multiple concurrent
  coroutines without `asyncio.Lock()` or `threading.Lock()` protection.
- **Thread-unsafe singleton or global state**: Module-level or class-level
  mutable state accessed and modified by multiple request handlers (Flask,
  Django) or async handlers without synchronization.
- **Concurrent database read-modify-write**: Database query followed by
  update in separate statements without SELECT FOR UPDATE or transaction
  isolation, allowing a concurrent request to modify the row between read
  and write.
- **File operations without flock**: Multiple concurrent processes writing
  to or reading from the same file without `fcntl.flock()` or `os.open()`
  with O_EXCL, risking interleaved writes or stale reads.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Session data race condition**: Concurrent requests to the same session
  ID modify session variables without explicit session locking
  (`session_write_close()` timing or serialize handlers).
- **Database operations without transaction**: Concurrent requests perform
  multiple SQL statements (select, then insert or update) without BEGIN
  TRANSACTION and SELECT ... FOR UPDATE, allowing race between statements.
- **File-based counters or state without locking**: Concurrent PHP
  processes read a file, modify its contents, and write back without
  `flock($handle, LOCK_EX)`, risking lost updates or stale values.
- **Shared memory operations (shmop) without synchronization**: Multiple
  processes access shared memory segments via `shmop_read()` and
  `shmop_write()` without semaphores (`sem_get()`, `sem_acquire()`).

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Promise.all with shared mutable state**: Multiple promises modify a
  shared object or array without locks or atomicity guarantees, leading to
  lost updates or data corruption.
- **Worker thread data races on SharedArrayBuffer**: Two or more Worker
  threads read and modify a SharedArrayBuffer without Atomics API, risking
  lost updates or visible intermediate states.
- **Event loop state mutation across async callbacks**: Request handler
  modifies a global or request-scoped variable across multiple `await`
  boundaries, allowing another event loop turn to modify it in between.
- **Redis/database check-then-act without atomic operations**: Fetches a
  value from Redis or database, checks it, then updates it in a separate
  operation without SETNX, Lua script, or transaction.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **Prisma or TypeORM concurrent modifications without transaction**:
  Multiple async operations read and modify the same database record across
  separate queries without `$transaction()` or `@Transaction()` decorator,
  allowing concurrent requests to interfere.
- **Shared mutable class properties in async context**: Class instance
  variables modified across `await` boundaries in async methods without
  synchronization, risking lost updates when multiple requests run
  concurrently.
- **Worker data races on SharedArrayBuffer**: Typed wrappers around
  SharedArrayBuffer read and write operations without Atomics API, risking
  lost updates.
- **Redis atomic operation misuse**: Promises that read and write Redis
  keys in separate `await` calls without Lua scripts or transaction, risking
  race between read and write.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the shared state access or the first
  observable modification.
- `meta.code_snippet`: 3-8 lines of source showing the concurrent access
  pattern.
- `meta.reasoning`: one sentence explaining the race condition window and
  why concurrent access is exploitable at this location.
- `meta.shared_resource`: the resource being accessed (variable name, table
  name, file path, Redis key).

Set `confidence`:

- `confirmed` when shared state is modified in an obviously concurrent
  context (asyncio coroutines, request handlers, Worker threads).
- `probable` when the shared resource is at global or class scope but
  concurrent access is inferred from context (e.g., web request handler
  touching module-level state).
- `potential` when the shared resource is inferred or the concurrent access
  pattern is not fully clear.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`design_logic.race_condition`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose: shared resource, concurrent access, race window>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-362"],
  "finding_type": ["vulnerability"],
  "rule_id": "design_logic.race_condition",
  "meta": {
    "title": "<short title, e.g. 'Asyncio race on shared dictionary'>",
    "owasp_name": "Insecure Design",
    "remediation": "<per-finding; see remediation guidance>",
    "code_snippet": "<3-8 lines of source showing concurrent access>",
    "shared_resource": "<variable, table, file, or key name>",
    "reasoning": "<one sentence explaining race condition>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library or
pattern observed in the code. Examples of good remediation strings:

- **asyncio shared state**: `Use asyncio.Lock() to protect access to the
  shared variable. Acquire the lock with `async with lock:` around all
  read-modify-write operations.`
- **Python thread-unsafe global state**: `Move the shared state into a
  request-scoped context (Flask `g` object, Django thread-local, or
  contextvars) or guard with threading.Lock().`
- **Python database race**: `Use SELECT ... FOR UPDATE to lock the row, or
  perform the check and update in a single atomic UPDATE statement with a
  WHERE clause on the condition.`
- **PHP session race**: `Call session_write_close() before concurrent
  operations to avoid session data races, or use session_regenerate_id()
  with locking.`
- **PHP file-based state**: `Use flock($handle, LOCK_EX) immediately after
  opening and hold it until the read-modify-write sequence is complete.`
- **JavaScript Promise.all race**: `Wrap the shared state access in a mutex
  or use Atomics API if using SharedArrayBuffer. For simple cases, avoid
  concurrent modifications and process results sequentially.`
- **JavaScript Redis race**: `Use Redis Lua scripts (EVAL) to ensure
  read-check-modify is atomic, or use client.SET(key, value, { NX: true })
  for simple set-if-not-exists patterns.`
- **TypeScript Prisma race**: `Wrap the transaction in prisma.$transaction()
  and perform all reads and writes within that scope to ensure isolation.`

Keep it two to four sentences. Reference the specific API or SQL pattern.

## Common false positives

- **Immutable data structures**: If the shared state is an immutable value
  (numbers, strings, tuples, frozen dataclasses), concurrent reads are safe;
  no false positive.
- **Read-only access**: Code that only reads from a shared resource without
  modifying it is safe; no race condition. Flag only if the resource is
  modified elsewhere in a concurrent context.
- **Single-threaded or single-coroutine code**: Code with no concurrency
  (CLI tools, simple scripts) has no race window; not flagged.
- **Guarded access (locks, semaphores, transactions)**: If shared state
  access is protected by a lock, semaphore, or database transaction, no
  race condition.
- **Queue-based processing**: Work queues (task queues, message brokers)
  inherently serialize work items; safe.
- **Atomic database operations**: INSERT ... ON CONFLICT, upsert operations,
  SELECT FOR UPDATE, transactions at SERIALIZABLE isolation: all safe.
- **Atomics API (SharedArrayBuffer)**: Proper use of `Atomics.load()`,
  `Atomics.store()`, `Atomics.compareExchange()` is safe; no race condition.
- **asyncio.Lock, asyncio.Semaphore, asyncio.Condition**: Proper use of
  asyncio synchronization primitives closes the race window.

## References

- `references/python.md`: Python patterns for asyncio, threading, database
  transactions, file locking.
- `references/php.md`: PHP patterns for session safety, database
  transactions, file locking, shared memory synchronization.
- `references/javascript.md`: Node patterns for Promise.all, Worker threads,
  asyncio-like state mutation, Redis atomicity.
- `references/typescript.md`: TypeScript patterns for Prisma, TypeORM,
  SharedArrayBuffer with Atomics, Redis transactions.
