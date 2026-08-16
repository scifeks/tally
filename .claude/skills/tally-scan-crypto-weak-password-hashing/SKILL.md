---
name: tally-scan-crypto-weak-password-hashing
description: >
  Scan the target repo for weak password hashing. Detects
  MD5, SHA1, and SHA256 used to hash passwords, unsalted
  hashing schemes, bcrypt or PBKDF2 with dangerously low
  iteration counts, and missing use of memory-hard KDFs
  like Argon2. Emits findings shaped for Tally MCP
  submission (rule_id crypto.weak_password_hashing,
  CWE-916, severity high). Invoke when the user says
  "password hashing", "weak password hash", "check for
  bcrypt cost", "Argon2", or when dispatched by
  tally-scan-external.
---

# Tally scanner: weak password hashing

Detects sinks where passwords are hashed with fast hash functions or
weak key derivation schemes. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.weak_password_hashing` |
| Primary CWE | `CWE-916` |
| Secondary CWE | `CWE-327` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `high` |
| Parent label (dedup) | `WeakPasswordHash` |


## Detection matrix

### Python

- **Fast hash on passwords**: `hashlib.md5(password.encode())`,
  `hashlib.sha1(password.encode())`,
  `hashlib.sha256(password.encode())` where the variable name
  or context indicates password storage.
- **Unsalted hashing**: any hash of a password without a
  unique-per-user salt.
- **Low bcrypt rounds**: `bcrypt.hashpw(password,
  bcrypt.gensalt(rounds=N))` where N < 10.
- **Low PBKDF2 iterations**: `hashlib.pbkdf2_hmac(...,
  iterations=N)` where N < 100000.
- **Deprecated passlib schemes**: `passlib.hash.md5_crypt`,
  `passlib.hash.des_crypt`, `passlib.hash.sha256_crypt` with
  low rounds.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Fast hash on passwords**: `md5($password)`,
  `sha1($password)`, `hash('sha256', $password)` where the
  variable name or context indicates password storage.
- **Weak crypt prefix**: `crypt($password, '$1$...')` (MD5),
  `crypt($password, 'ab')` (DES). Safe prefixes are `$2y$`
  (bcrypt) and `$argon2id$`.
- **Low bcrypt cost**: `password_hash($password,
  PASSWORD_BCRYPT, ['cost' => N])` where N < 10. PHP default
  cost is 10.
- **Missing password_hash**: custom hashing instead of
  `password_hash()` / `password_verify()`.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Fast hash on passwords**:
  `crypto.createHash('sha256').update(password).digest('hex')`,
  `crypto.createHash('md5').update(password)...` where the
  variable name or context indicates password storage.
- **Low bcrypt rounds**: `bcrypt.hashSync(password, N)` where
  N < 10.
- **Low PBKDF2 iterations**: `crypto.pbkdf2Sync(password,
  salt, N, ...)` where N < 100000.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

Same Node.js sinks as JavaScript apply. Additionally:

- Typed password-handling functions that accept a `string`
  password and return a `string` hash via a fast hash function.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  defect at this location.
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
`crypto.weak_password_hashing`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink, the source, and what
  an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-916", "CWE-327"],
  "finding_type": ["vulnerability"],
  "rule_id": "crypto.weak_password_hashing",
  "meta": {
    "title": "<short human title, e.g. 'Weak password hashing
    via MD5'>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding; see remediation
    guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable,
    when traceable>",
    "reasoning": "<one sentence explaining the defect at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation
strings:

- **Python hashlib on password**: Use bcrypt:
  `bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))`.
  For new systems, prefer Argon2:
  `argon2.PasswordHasher().hash(password)`.
- **PHP md5/sha1 on password**: Use
  `password_hash($password, PASSWORD_ARGON2ID)`. If Argon2 is
  unavailable, use `PASSWORD_BCRYPT` with the default cost (10).
- **Node.js createHash on password**: Use bcrypt:
  `await bcrypt.hash(password, 12)`. For new systems, prefer
  argon2: `await argon2.hash(password)`.
- **Low rounds/iterations**: Increase bcrypt cost to at least
  12. Increase PBKDF2 iterations to at least 600000 per current
  OWASP guidance.

Keep it two to four sentences. Vague guidance ("use bcrypt") is
worse than no guidance.

## Common false positives

- **Hashing non-password data**: `hashlib.sha256(data)` where
  `data` is not a password (file checksums, cache keys, content
  hashes). Check the variable name and context.
- **Verification calls**: `password_verify($input, $hash)` or
  `bcrypt.compare(input, hash)` are verification, not hashing.
- **Test fixtures**: hardcoded password hashes in test setup
  that do not run in production.
- **Comments and documentation**: algorithm names in comments
  describing migration plans.

## References

- `references/python.md`: Python patterns for hashlib, bcrypt,
  argon2, PBKDF2, scrypt.
- `references/php.md`: PHP patterns for md5, sha1, crypt,
  password_hash, Sodium.
- `references/javascript.md`: Node patterns for crypto.createHash,
  bcrypt, PBKDF2, argon2, scrypt.
- `references/typescript.md`: TypeScript patterns for Node.js
  crypto module.
