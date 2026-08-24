---
name: tally-scan-crypto-weak-prng
description: >
  Scan the target repo for weak PRNG usage in security contexts.
  Detects Math.random(), random.random(), mt_rand(), and similar
  non-cryptographic PRNGs used to generate tokens, session IDs,
  nonces, CSRF tokens, OTPs, or encryption keys. Emits findings
  shaped for Tally MCP submission (rule_id crypto.weak_prng,
  CWE-338, severity medium). Invoke when the user says "weak PRNG",
  "Math.random", "random for tokens", "predictable token", or when
  dispatched by tally-scan-external.
---

# Tally scanner: weak PRNG for security context

Detects sinks where non-cryptographic PRNGs generate values for
security-sensitive purposes. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or standalone
when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.weak_prng` |
| Primary CWE | `CWE-338` |
| Secondary CWE | `CWE-330` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `medium` |
| Parent label (dedup) | `WeakPRNG` |


## Detection matrix

### Python

- **`random` module in security context**: `random.random()`,
  `random.randint()`, `random.choice()`, `random.getrandbits()`,
  `random.shuffle()` used to generate tokens, session IDs, nonces,
  CSRF tokens, OTPs, passwords, or encryption keys.
- **`uuid.uuid1()` for security tokens**: UUID1 is time-based and
  partially predictable. Safe form for tokens is `uuid.uuid4()`.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **`rand()` and `mt_rand()`**: used for tokens, passwords, nonces,
  or session IDs. `mt_rand()` is Mersenne Twister, deterministic
  after observing 624 outputs.
- **`array_rand()` and `shuffle()`**: used to generate random
  selections in security contexts.
- **`uniqid()`**: time-based, trivially predictable. Not suitable for
  tokens or secret values.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **`Math.random()`**: used for tokens, session IDs, nonces,
  passwords, keys, or any security-sensitive random value.
  `Math.random()` is not cryptographically secure on any JavaScript
  engine.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

Same sinks as JavaScript. `Math.random()` typed as `number` is the
primary pattern.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  weak PRNG at this location.
- When the taint source is in the same file:
  `meta.taint_source` naming the request parameter or upstream
  variable that reaches the sink.

Set `confidence`:

- `confirmed` when a taint source is traced from a request handler
  to the sink in the same file, or through a same-file helper.
- `probable` when the sink pattern matches and the value is
  clearly a variable (not a constant), but the source is inferred.
- `potential` when the sink is suspicious but the value is not
  obviously used for security.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`crypto.weak_prng`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink and security impact>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-338", "CWE-330"],
  "finding_type": ["vulnerability"],
  "rule_id": "crypto.weak_prng",
  "meta": {
    "title": "<short human title>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining why the weak PRNG is used>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library observed in the code. Examples of good remediation strings:

- **Python random**: `Use the secrets module: secrets.token_hex(32)
  for tokens, secrets.token_urlsafe(32) for URL-safe tokens,
  secrets.randbelow(n) for bounded integers.`
- **PHP mt_rand**: `Use random_int(min, max) for integers or
  bin2hex(random_bytes(32)) for hex tokens. Both use the OS
  CSPRNG.`
- **JavaScript Math.random**: `Use crypto.randomBytes(32) for raw
  bytes, crypto.randomUUID() for UUIDs, or
  crypto.getRandomValues(new Uint8Array(32)) in browser contexts.`

Keep it two to four sentences. Vague guidance ("use a cryptographic
PRNG") is worse than no guidance.

## Common false positives

- **Non-security uses**: `random.shuffle()` for UI element ordering,
  `Math.random()` for animation offsets, `mt_rand()` for test data
  generation. These are not security-sensitive.
- **Seeded deterministic sequences**: `random.seed(42)` in test
  fixtures or reproducible simulations.
- **Wrapped in a non-security context**: `Math.random()` used to
  pick a random greeting message or color.

## References

- `references/python.md`: Python patterns for random, uuid, os.urandom.
- `references/php.md`: PHP patterns for rand, mt_rand, random_bytes.
- `references/javascript.md`: Node patterns for Math.random,
  crypto.randomBytes, Web Crypto API.
- `references/typescript.md`: TypeScript patterns for node:crypto.
