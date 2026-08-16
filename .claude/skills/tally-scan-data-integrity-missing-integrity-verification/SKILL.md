---
name: tally-scan-data-integrity-missing-integrity-verification
description: >
  Scan the target repo for missing data integrity verification defects.
  Detects unsigned artifact downloads, webhook HMAC bypass, JWT signature
  skipping, and plugin loading without hash pinning. Emits findings shaped
  for Tally MCP submission (rule_id
  `data_integrity.missing_integrity_verification`, CWE-345, severity high).
  Invoke when the user says "integrity verification", "missing signature
  check", "webhook HMAC", "unsigned download", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: Missing data integrity verification

Detects sinks where integrity checks (checksums, signatures, HMAC
validation) are missing on data that should be trusted. Runs per-file in
the target repo (as dispatched by the `tally-scan-external` orchestrator,
or standalone when the user invokes this skill directly). Emits a JSON
list of findings; the orchestrator or the user submits them to Tally
through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `data_integrity.missing_integrity_verification` |
| Primary CWE | `CWE-345` |
| OWASP 2025 category | `Software or Data Integrity Failures` |
| Default severity | `high` |
| Parent label (dedup) | `MissingIntegrity` |


## Detection matrix

### Python

- **Unsigned HTTP download**: `requests.get()`, `urllib.request.urlopen()`,
  or `httpx.get()` fetching a binary, script, or config file followed by
  execution, loading, or use without checksum verification against a
  known-good hash.
- **Webhook HMAC bypass**: a request handler reading `request.body` or
  `request.data` without verifying the HMAC signature against a header
  like `X-Hub-Signature-256` (GitHub) or `X-Signature` (generic).
- **JWT signature disabled**: `jwt.decode()` (PyJWT) with
  `options={"verify_signature": False}` or `algorithms=["none"]`.
- **Subprocess on downloaded artifact**: `subprocess.run()`, `subprocess.call()`,
  or `exec()` on a script or config file sourced from a URL without prior
  hash or signature check.
- **Plugin/extension loading from URL**: dynamic module loading
  (`importlib.import_module()`, `__import__()`) of code from a URL without
  hash pinning.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Unsigned file download**: `file_get_contents($url)` or curl-based
  download of a binary or script without `hash_file()` verification.
- **Webhook HMAC bypass**: reading `php://input` or `$_SERVER['REQUEST_BODY']`
  without `hash_hmac()` + `hash_equals()` signature verification against a
  header.
- **JWT verification disabled**: Firebase JWT `JWT::decode()` without a
  key or with `$allowedAlgos = ["none"]`.
- **Remote include/require**: `include()` or `require()` on a file path
  that came from a URL without prior integrity check.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Unsigned fetch/axios download**: `fetch()`, `axios.get()`, `got()`, or
  `node-fetch` downloading an artifact without computing and validating a
  checksum or signature.
- **Webhook handler HMAC bypass**: Express, Koa, or raw Node.js request
  handler reading `req.body` or `req.rawBody` without
  `crypto.createHmac()` + `crypto.timingSafeEqual()` verification.
- **JWT signature verification disabled**: `jsonwebtoken.verify()` with
  `algorithms: ['none']` or without specifying `algorithms` (which allows
  "none" by default in some versions).
- **Dynamic module import without integrity**: `import(userInput)` or
  `require(userInput)` where the path comes from external input without
  hash validation.

Read `references/javascript.md` for vulnerable-vs-safe code patterns.

### TypeScript

- **Typed wrapper around unsigned download**: the same patterns as
  JavaScript applied to typed fetch clients or axios instances.
- **NestJS guards without HMAC validation**: a route guard or middleware
  validating webhook signatures using only `jwt-decode` (which does not
  verify signatures) instead of `jsonwebtoken.verify()`.
- **jose or other JWT library with missing `alg` enforcement**: using jose
  or another JWT library without explicitly validating the algorithm is
  one of a known-good set.
- Same JavaScript sinks apply on the Node runtime.

Read `references/typescript.md` for vulnerable-vs-safe code patterns.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call (the fetch, webhook
  handler, jwt.decode, exec, or include).
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the integrity check is
  missing at this location.
- When the artifact source is traceable in the same file:
  `meta.taint_source` naming the variable or parameter that carries the
  untrusted data.

Set `confidence`:

- `confirmed` when the sink pattern is explicit (jwt.decode with
  verify_signature=False, fetch with no checksum visible, webhook without
  HMAC) and the intent is clear.
- `probable` when the pattern matches but there is uncertainty about
  whether a checksum is verified elsewhere.
- `potential` when the pattern is suspicious but context is insufficient
  to confirm the defect.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`data_integrity.missing_integrity_verification`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the unverified data and attack>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-345"],
  "finding_type": ["vulnerability"],
  "rule_id": "data_integrity.missing_integrity_verification",
  "meta": {
    "title": "<short human title, e.g. 'Unsigned artifact download'>",
    "owasp_name": "Software or Data Integrity Failures",
    "remediation": "<per-finding; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<URL, request parameter, or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining why the integrity check is missing>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library and
use case observed in the code. Examples of good remediation strings:

- **Python artifact download**: `Compute hashlib.sha256(downloaded_bytes).hexdigest()
  after the fetch. Compare the result to a known-good hash (e.g., from a
  config file or environment variable). Reject the artifact if the hashes
  do not match.`
- **Python webhook HMAC**: `Compute expected_signature = hmac.new(secret,
  request.body, hashlib.sha256).hexdigest(). Extract the signature from
  the request header (e.g., request.headers.get('X-Hub-Signature-256'))
  and compare with hmac.compare_digest(expected_signature, header_value).
  Reject the request if the signatures do not match.`
- **Python JWT**: `Replace options={'verify_signature': False} with
  options={'verify_signature': True}. Always pass an explicit algorithms
  list: jwt.decode(token, secret, algorithms=['HS256']). Never include
  'none' in the algorithms list.`
- **PHP artifact download**: `After file_get_contents($url), compute
  hash_file('sha256', $filename) and compare it to a known-good hash.
  Reject the file if the hashes do not match.`
- **PHP webhook**: `Compute $expected = hash_hmac('sha256', $payload,
  $secret). Extract the signature from $_SERVER['HTTP_X_SIGNATURE'] or
  similar. Compare with hash_equals($expected, $signature). Reject the
  request if they do not match.`
- **JavaScript fetch**: `After fetch(), read the response body, compute
  crypto.createHash('sha256').update(body).digest('hex'), and compare to
  a known-good hash. Reject if they do not match.`
- **JavaScript webhook**: `Compute the expected HMAC with
  crypto.createHmac('sha256', secret).update(rawBody).digest('hex'). Extract
  the signature from the request header. Compare with
  crypto.timingSafeEqual(Buffer.from(expected),
  Buffer.from(headerValue)). Reject the request on mismatch. Use the raw
  body buffer, not the parsed JSON.`
- **JavaScript JWT**: `Always pass an explicit algorithms array to
  jsonwebtoken.verify(): verify(token, secret, {algorithms: ['HS256']}). Never
  allow 'none'.`

Keep it two to four sentences. Reference the specific function name,
library, and algorithm. Vague guidance ("verify integrity") is worse than
no guidance.

## Common false positives

- **Package manager downloads**: downloads from npm, pip, composer, or yarn
  that are protected by lockfile hashes (package-lock.json, requirements.txt
  with hashes, composer.lock) already include integrity checks at the
  ecosystem level. Do not flag these.
- **Internal API over mTLS**: API calls to a trusted internal service over
  mTLS where transport-layer encryption and authentication suffice do not
  need application-level integrity checks. Verify the call is internal and
  protected.
- **JWT with library defaults**: a JWT library that enforces algorithm
  validation by default does not need an explicit `algorithms` parameter.
  Verify the library's documented behavior before flagging.
- **jwt-decode for UI display only**: the `jwt-decode` package is
  legitimate for decoding and displaying JWT claims in the browser UI
  (not for authorization). Do not flag if the claim is only used for
  display, not for security decisions.
- **Checksum verification in a separate function**: if the checksum
  download and verification happen in different functions within the same
  file, trace the flow before flagging. If verification is always called
  after download, the pattern is safe.
- **Signature verification delegated to a trusted library**: if a webhook
  handler uses a framework or package that handles HMAC verification
  transparently (e.g., a middleware that validates signatures before
  reaching the handler), do not flag the handler itself.

## References

- `references/python.md`: Python patterns for requests, urllib, httpx,
  PyJWT, webhook handling, and subprocess.
- `references/php.md`: PHP patterns for file operations, curl, webhook
  handling, and Firebase JWT.
- `references/javascript.md`: Node.js patterns for fetch, axios, Express,
  Koa, jsonwebtoken, and dynamic imports.
- `references/typescript.md`: TypeScript patterns for typed HTTP clients,
  NestJS, jose, and Node.js runtime.
