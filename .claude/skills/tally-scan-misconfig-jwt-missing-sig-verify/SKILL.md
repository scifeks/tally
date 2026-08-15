---
name: tally-scan-misconfig-jwt-missing-sig-verify
description: >
  Scan the target repo for missing JWT signature verification.
  Detects jwt.decode() calls without verification, verify=False
  options, algorithms=["none"] acceptance, and decode-without-verify
  patterns across JWT libraries. Emits findings shaped for Tally
  MCP submission (rule_id `misconfig.jwt_missing_sig_verify`,
  CWE-347, severity critical). Invoke when the user says "JWT
  signature", "missing JWT verification", "unsigned JWT", or when
  dispatched by `tally-scan-external`.
---

# Tally scanner: Missing JWT signature verification

Detects code paths where a JWT is decoded or consumed without
verifying its cryptographic signature, allowing an attacker to
forge tokens with arbitrary claims. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a
JSON list of findings; the orchestrator or the user submits them to
Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.jwt_missing_sig_verify` |
| Primary CWE | `CWE-347` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `critical` |
| Parent label (dedup) | `JWT` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 25.

## Detection matrix

### Python

- **PyJWT `decode` with verify disabled**: `jwt.decode(token,
  options={"verify_signature": False})`. This decodes the token
  without checking the signature.
- **PyJWT `decode` with `algorithms=["none"]`**:
  `jwt.decode(token, algorithms=["none"])`. Accepts unsigned
  tokens.
- **python-jose disabled verification**:
  `jwt.decode(token, None, options={"verify_signature": False})`
  or `jwt.decode(token, None, algorithms=["none"])`.
- **authlib disabled verification**: `jwt.decode(token, None)` or
  calling decode without a key when the library allows it.
- **PyJWT `decode` vs `decode_complete`**: both methods accept
  the `options` dict; check both for disabled verification.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **firebase/php-jwt decode without key**: calling
  `JWT::decode($token)` without a valid key parameter, or passing
  an empty string as the key.
- **Custom JWT handling**: `base64_decode()` +
  `json_decode()` on the token payload without verifying the
  signature segment. Common in legacy code that "parses" JWTs
  manually.
- **lcobucci/jwt missing verification**: parsing a token with
  `(new Parser())->parse($token)` and reading claims without
  calling `->verify()` or `->assert()` with a validator.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **jsonwebtoken `decode` vs `verify`**: `jwt.decode(token)`
  returns the payload without signature verification.
  `jwt.verify(token, secret)` verifies the signature.
  Using `decode` for access-control decisions is the defect.
- **jose `decodeJwt` without verification**:
  `decodeJwt(token)` returns claims without verification.
  The safe equivalent is `jwtVerify(token, key)`.
- **jose `decodeProtectedHeader` as sole check**: reading
  the header with `decodeProtectedHeader(token)` and acting
  on claims without a subsequent `jwtVerify()` call.

Defer to `references/javascript.md` for vulnerable-vs-safe
snippets.

### TypeScript

- **jsonwebtoken `decode`**: same as JavaScript.
  `jwt.decode(token)` is typed as
  `string | JwtPayload | null`; the return type does not
  signal that the payload is unverified.
- **jose `decodeJwt`**: same as JavaScript. TypeScript types
  do not prevent use of `decodeJwt` for access decisions.

Defer to `references/typescript.md` for vulnerable-vs-safe
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the decode or
  verification-skip call.
- `meta.code_snippet`: 2-6 lines of source containing the call.
- `meta.reasoning`: one sentence explaining why the token is
  consumed without signature verification.
- When the token source is visible: `meta.taint_source` naming
  where the token comes from (e.g. "Authorization header",
  "cookie", "query parameter").

Set `confidence`:

- `confirmed` when the code calls `decode` (not `verify`) and
  uses the returned claims for access-control decisions in the
  same file.
- `probable` when `verify_signature: False` or
  `algorithms: ["none"]` is set, regardless of how the claims
  are used downstream.
- `potential` when `decode` is called but the claims might be
  used only for logging or non-security purposes.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.jwt_missing_sig_verify`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the missing verification>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-347"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.jwt_missing_sig_verify",
  "meta": {
    "title": "<short title, e.g. 'JWT decoded without signature verification'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<token source, when traceable>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual
library observed in the code. Examples:

- **PyJWT**: `Replace jwt.decode() with jwt.decode(token, key,
  algorithms=["RS256"]). Always pass the signing key and an
  explicit algorithms list. Remove any
  options={"verify_signature": False} arguments.`
- **python-jose**: `Replace jwt.decode(token, None, ...) with
  jwt.decode(token, key, algorithms=["RS256"]). Pass the
  public key or shared secret as the second argument.`
- **jsonwebtoken (Node)**: `Replace jwt.decode(token) with
  jwt.verify(token, secret, { algorithms: ["HS256"] }).
  jwt.decode() only decodes without verification; jwt.verify()
  checks the signature.`
- **jose (Node)**: `Replace decodeJwt(token) with
  jwtVerify(token, key). The decodeJwt function does not verify
  the signature; use it only for non-security inspection.`
- **firebase/php-jwt**: `Pass a valid Key object to
  JWT::decode(): JWT::decode($token, new Key($publicKey,
  "RS256")). Never decode without a key.`
- **Custom JWT parsing**: `Do not manually decode JWT segments
  with base64_decode(). Use a maintained JWT library
  (firebase/php-jwt, lcobucci/jwt) that handles signature
  verification and claim validation.`

Keep it two to four sentences.

## Common false positives

- **Logging or debugging**: `jwt.decode(token)` used to log
  token claims for debugging, where the decoded values never
  influence access-control decisions. Still flag but set
  confidence to `potential`.
- **Token introspection endpoints**: endpoints that return
  decoded token metadata to the token holder. These are
  intentionally non-verifying if the caller already holds
  the token.
- **Pre-verification header inspection**: calling
  `decodeProtectedHeader(token)` to read the `kid` (key ID)
  before selecting the correct key for a subsequent `jwtVerify()`
  call. This is safe as long as `jwtVerify()` runs before any
  access decision.
- **Test code**: `jwt.decode()` in test fixtures or test helpers
  that construct tokens for testing. Do not flag test files.

## References

- `references/python.md`: PyJWT, python-jose patterns.
- `references/php.md`: firebase/php-jwt, lcobucci/jwt,
  custom parsing patterns.
- `references/javascript.md`: jsonwebtoken, jose patterns.
- `references/typescript.md`: typed jsonwebtoken, jose patterns.
