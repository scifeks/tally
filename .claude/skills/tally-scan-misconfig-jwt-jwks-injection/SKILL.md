---
name: tally-scan-misconfig-jwt-jwks-injection
description: >
  Scan the target repo for JWT JWKS injection or key confusion
  defects. Detects JWKS endpoint URLs sourced from the token's
  jku header, trusted embedded JWK claims, untrusted x5u
  certificate URLs, and missing key ID validation. Emits findings
  shaped for Tally MCP submission (rule_id
  `misconfig.jwt_jwks_injection`, CWE-345, severity critical).
  Invoke when the user says "JWKS injection", "jku injection",
  "JWT key confusion", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: JWT JWKS injection

Detects code paths where the key used to verify a JWT is sourced
from the token itself (via `jku`, `x5u`, or embedded `jwk` header
claims), allowing an attacker to supply their own signing key and
forge valid tokens. Runs per-file in the target repo (as
dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a
JSON list of findings; the orchestrator or the user submits them
to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.jwt_jwks_injection` |
| Primary CWE | `CWE-345` |
| Secondary CWE | `CWE-347` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `critical` |
| Parent label (dedup) | `JWT` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 27.

## Detection matrix

### Python

- **PyJWKClient with token-sourced URL**: constructing
  `PyJWKClient(url)` where `url` comes from the decoded token's
  `jku` header claim. The JWKS URL must be server-configured,
  not token-sourced.
- **Embedded JWK from token header**: extracting the `jwk` claim
  from the token header and using it as the verification key
  without validating against a known key set.
- **authlib trusting jku**: calling `jwt.decode()` with a key
  fetcher that follows the token's `jku` URL without an
  allowlist.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **JWKS URL from token header**: decoding the token header with
  `json_decode(base64_decode(...))`, reading the `jku` field,
  and fetching keys from that URL with `file_get_contents()` or
  a Guzzle request.
- **Embedded JWK from token**: reading the `jwk` claim from the
  token header and using it directly as the verification key.
- **x5u certificate URL**: fetching an X.509 certificate chain
  from the token's `x5u` header without verifying the URL
  against an allowlist.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **jose `createRemoteJWKSet` with token URL**: calling
  `createRemoteJWKSet(new URL(header.jku))` where `header` is
  extracted from the unverified token. The JWKS URL must be
  hardcoded or from server configuration.
- **Embedded JWK from token**: using `importJWK(header.jwk)` to
  import a key from the token header without checking it against
  a trusted key store.
- **jsonwebtoken with token-sourced key**: selecting the
  verification key based on unverified token header claims
  without restricting the key source.

Defer to `references/javascript.md` for vulnerable-vs-safe
snippets.

### TypeScript

- **jose `createRemoteJWKSet` with token URL**: same as
  JavaScript. TypeScript types accept any `URL` instance; they
  do not restrict the URL source.
- **Embedded JWK import**: same as JavaScript.

Defer to `references/typescript.md` for vulnerable-vs-safe
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the key-fetch or
  key-import call that uses token-sourced data.
- `meta.code_snippet`: 2-6 lines of source showing the token
  header extraction and key usage.
- `meta.reasoning`: one sentence explaining how an attacker
  can inject their own key.
- When the header extraction is visible: `meta.taint_source`
  naming the header claim used (`jku`, `x5u`, or `jwk`).

Set `confidence`:

- `confirmed` when the code visibly extracts a URL or key from
  the unverified token header and uses it for verification in
  the same file.
- `probable` when a JWKS URL variable is populated from a
  function that reads token headers, but the function body is
  in another file.
- `potential` when a `createRemoteJWKSet` or `PyJWKClient` call
  uses a variable whose origin is unclear.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.jwt_jwks_injection`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the JWKS injection>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-345", "CWE-347"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.jwt_jwks_injection",
  "meta": {
    "title": "<short title, e.g. 'JWKS URL sourced from token jku header'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19>",
    "code_snippet": "<2-6 lines of source>",
    "taint_source": "<header claim: jku, x5u, or jwk>",
    "reasoning": "<one sentence explaining the defect>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual
library observed in the code. Examples:

- **PyJWKClient with hardcoded URL**: `Pin the JWKS URL in
  server configuration: PyJWKClient("https://auth.example.com/
  .well-known/jwks.json"). Never read the URL from the token's
  jku header claim.`
- **jose createRemoteJWKSet**: `Hardcode the JWKS URL:
  createRemoteJWKSet(new URL("https://auth.example.com/
  .well-known/jwks.json")). Do not construct the URL from the
  token header.`
- **Embedded JWK from token**: `Do not import keys from the
  token's jwk header claim. Load the signing key from a
  server-side key store, environment variable, or a pinned
  JWKS endpoint.`
- **x5u header trust**: `Do not fetch certificates from the
  token's x5u header. Pin the certificate URL in server
  configuration or embed the certificate directly.`
- **PHP JWKS fetch**: `Hardcode the JWKS endpoint URL in
  configuration. Validate the kid from the token header against
  the keys returned by the pinned endpoint, but never let the
  token control which endpoint is fetched.`

Keep it two to four sentences.

## Common false positives

- **Hardcoded JWKS URL**: `createRemoteJWKSet(new URL(
  "https://auth.example.com/.well-known/jwks.json"))` with a
  string literal URL is safe. The URL does not come from the
  token.
- **JWKS URL from environment variable**: `PyJWKClient(
  os.environ["JWKS_URL"])` is safe. The URL comes from server
  configuration, not from the token.
- **kid-based key selection from a local store**: reading the
  `kid` from the token header to select a key from a
  server-side key map is safe. The key itself is not
  token-sourced; only the key identifier is.
- **Token issuance (signing) code**: code that embeds a `jku`
  or `jwk` header when signing a token is not a JWKS injection
  vulnerability. The risk is on the verification side.

## References

- `references/python.md`: PyJWKClient and authlib patterns.
- `references/php.md`: JWKS fetch and embedded JWK patterns.
- `references/javascript.md`: jose and jsonwebtoken key
  sourcing patterns.
- `references/typescript.md`: typed jose key sourcing patterns.
