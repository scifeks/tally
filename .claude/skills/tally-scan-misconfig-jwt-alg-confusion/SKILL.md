---
name: tally-scan-misconfig-jwt-alg-confusion
description: >
  Scan the target repo for JWT algorithm confusion or downgrade
  defects. Detects verification calls that accept both symmetric
  and asymmetric algorithms, missing algorithm restrictions, and
  algorithm selection derived from the token header. Emits
  findings shaped for Tally MCP submission (rule_id
  `misconfig.jwt_alg_confusion`, CWE-757, severity critical).
  Invoke when the user says "JWT algorithm confusion",
  "JWT alg confusion", "algorithm downgrade", or when dispatched
  by `tally-scan-external`.
---

# Tally scanner: JWT algorithm confusion

Detects code paths where the JWT verification step accepts
multiple algorithm families (symmetric and asymmetric) or derives
the algorithm from the token header, allowing an attacker to
forge a valid signature by switching algorithm types. Runs
per-file in the target repo (as dispatched by the
`tally-scan-external` orchestrator, or standalone when the user
invokes this skill directly). Emits a JSON list of findings; the
orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.jwt_alg_confusion` |
| Primary CWE | `CWE-757` |
| Secondary CWE | `CWE-347` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `critical` |
| Parent label (dedup) | `JWT` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 26.

## Detection matrix

### Python

- **PyJWT mixed algorithms**: `jwt.decode(token, key,
  algorithms=["HS256", "RS256"])`. Accepting both families
  lets an attacker sign with HS256 using the RSA public key as
  the HMAC secret.
- **PyJWT missing algorithms**: `jwt.decode(token, key)` without
  an explicit `algorithms` argument. Older PyJWT versions
  defaulted to accepting any algorithm; current versions require
  the parameter but legacy code may suppress the warning.
- **python-jose mixed algorithms**: same pattern as PyJWT.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **firebase/php-jwt mixed key types**: passing a key array
  that maps multiple algorithm families:
  `['kid1' => new Key($rsaKey, 'RS256'),
  'kid2' => new Key($hmacSecret, 'HS256')]`.
- **Algorithm from token header**: reading `$header->alg` from
  the decoded token header and using it to select the
  verification algorithm instead of enforcing a server-side
  algorithm.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **jsonwebtoken missing algorithms option**:
  `jwt.verify(token, key)` without `{ algorithms: [...] }`.
  Without the restriction, the library may accept whichever
  algorithm the token header declares.
- **Algorithm from token header**: `const alg =
  jwt.decode(token, { complete: true }).header.alg;` followed
  by using `alg` to select the verification key or algorithm.
- **jose missing algorithms**: `jwtVerify(token, key)` without
  an `algorithms` option. The `jose` library restricts by key
  type by default, but explicit restriction is safer.

Defer to `references/javascript.md` for vulnerable-vs-safe
snippets.

### TypeScript

- **jsonwebtoken missing algorithms**: same as JavaScript.
  TypeScript's types for `VerifyOptions` include `algorithms`
  as optional, so omitting it compiles without error.
- **jose missing algorithms**: same as JavaScript.

Defer to `references/typescript.md` for vulnerable-vs-safe
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the verification call
  with the algorithm confusion.
- `meta.code_snippet`: 2-6 lines of source containing the
  verify call and its options.
- `meta.reasoning`: one sentence explaining how the algorithm
  confusion is exploitable.
- When the key material is visible: `meta.taint_source` noting
  whether the key is symmetric (shared secret) or asymmetric
  (public/private pair).

Set `confidence`:

- `confirmed` when the code explicitly lists both HS* and RS*
  (or ES*, PS*) algorithms in the same verification call.
- `probable` when the algorithms parameter is missing and the
  library's default behavior accepts multiple families.
- `potential` when the algorithm is read from the token header
  but a downstream check may restrict it.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.jwt_alg_confusion`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the algorithm confusion>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-757", "CWE-347"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.jwt_alg_confusion",
  "meta": {
    "title": "<short title, e.g. 'JWT accepts both HS256 and RS256'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<key type info, when visible>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual
library observed in the code. Examples:

- **PyJWT**: `Restrict the algorithms list to a single family:
  jwt.decode(token, key, algorithms=["RS256"]). Never include
  both HS* and RS* in the same list. If the application uses
  RS256, the key must be the RSA public key, not a shared
  secret.`
- **jsonwebtoken (Node)**: `Pass an explicit algorithms option:
  jwt.verify(token, key, { algorithms: ["RS256"] }). Without
  this option, the library may accept the algorithm declared in
  the token header.`
- **jose (Node)**: `Pass algorithms in the options:
  jwtVerify(token, key, { algorithms: ["RS256"] }). The jose
  library restricts by key type by default, but explicit
  restriction prevents future regressions.`
- **firebase/php-jwt**: `Map each key ID to a single algorithm:
  JWT::decode($token, new Key($publicKey, "RS256")). Do not
  mix HMAC and RSA keys in the same key array.`
- **Algorithm from header**: `Never derive the verification
  algorithm from the token header. The server must decide which
  algorithm to accept. Read the kid from the header to select
  a key, but verify with a server-configured algorithm.`

Keep it two to four sentences.

## Common false positives

- **Multiple algorithms of the same family**: accepting
  `["RS256", "RS384", "RS512"]` is safe because all three are
  asymmetric RSA algorithms. The confusion attack requires
  mixing symmetric and asymmetric families.
- **Key-type enforcement by library**: the `jose` library binds
  the algorithm to the key type at verification time. If the
  key is an RSA `CryptoKey`, only RS*/PS* algorithms are
  accepted regardless of the `algorithms` option. Still flag
  the missing restriction for defense in depth.
- **Token issuance (signing) code**: algorithm confusion is a
  verification-side defect. A `jwt.sign()` call with
  `algorithm: "HS256"` is not a confusion vulnerability; the
  signer controls the algorithm.

## References

- `references/python.md`: PyJWT, python-jose algorithm patterns.
- `references/php.md`: firebase/php-jwt algorithm patterns.
- `references/javascript.md`: jsonwebtoken, jose algorithm
  patterns.
- `references/typescript.md`: typed jsonwebtoken, jose patterns.
