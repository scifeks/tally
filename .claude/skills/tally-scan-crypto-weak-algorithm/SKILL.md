---
name: tally-scan-crypto-weak-algorithm
description: >
  Scan the target repo for use of weak or deprecated
  cryptographic algorithms. Detects DES, 3DES, RC4,
  Blowfish, ECB mode, MD5/SHA1 for integrity or
  authentication, and RSA keys under 2048 bits. Emits
  findings shaped for Tally MCP submission (rule_id
  crypto.weak_algorithm, CWE-327, severity high).
  Invoke when the user says "weak crypto", "weak
  algorithm", "check for DES", "deprecated cipher",
  or when dispatched by tally-scan-external.
---

# Tally scanner: weak cryptographic algorithm

Detects sinks where weak or deprecated cryptographic algorithms are used
for encryption, hashing, or key generation. Runs per-file in the target
repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list
of findings; the orchestrator or the user submits them to Tally through
the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.weak_algorithm` |
| Primary CWE | `CWE-327` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `high` |
| Parent label (dedup) | `WeakCrypto` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 5.

## Detection matrix

### Python

- **Deprecated cipher import**: `from Crypto.Cipher import DES`,
  `DES3`, `ARC4`, `Blowfish` (PyCryptodome). Safe form uses
  `AES` in GCM or CBC mode.
- **Weak algorithm via cryptography lib**:
  `algorithms.TripleDES`, `algorithms.ARC4`,
  `algorithms.Blowfish`, `algorithms.IDEA`. Safe form uses
  `algorithms.AES`.
- **ECB mode**: `modes.ECB` on any block cipher. ECB does not
  provide semantic security. Safe form uses `modes.GCM`,
  `modes.CBC`, or `modes.CTR`.
- **MD5/SHA1 for integrity or authentication**:
  `hashlib.md5(data)` or `hashlib.sha1(data)` where the result
  guards a security decision (HMAC, signature, token
  derivation). Safe form uses `hashlib.sha256` or higher.
- **Small RSA key**: `rsa.generate_private_key(
  public_exponent=65537, key_size=1024)`. Safe form uses
  `key_size=2048` or higher.
- **Deprecated hashlib call**: `hashlib.new('md4', data)`.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **mcrypt extension**: any `mcrypt_encrypt`, `mcrypt_decrypt`,
  `mcrypt_cbc`, `mcrypt_ecb` call. The entire mcrypt extension
  is removed in PHP 7.2+. Safe form uses `openssl_encrypt`
  with `aes-256-gcm` or `sodium_crypto_secretbox`.
- **Weak OpenSSL cipher**: `openssl_encrypt($data, 'des-ecb',
  ...)`, `openssl_encrypt($data, 'des-ede3-cbc', ...)`,
  `openssl_encrypt($data, 'rc4', ...)`,
  `openssl_encrypt($data, 'bf-cbc', ...)`. Safe form uses
  `aes-256-gcm` or `aes-256-cbc`.
- **ECB mode in OpenSSL**: any cipher string ending in `-ecb`.
- **MD5/SHA1 for integrity**: `md5($data)` or `sha1($data)`
  where the result guards a security decision. Safe form uses
  `hash('sha256', $data)` or `hash_hmac('sha256', ...)`.
- **Small RSA key**: `openssl_pkey_new(['private_key_bits' =>
  1024])`. Safe form uses 2048 or higher.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Deprecated createCipher**: `crypto.createCipher('des', key)`
  (deprecated API with weak key derivation). Safe form uses
  `crypto.createCipheriv('aes-256-gcm', key, iv)`.
- **Weak algorithm in createCipheriv**: `des`, `des-ede3`,
  `rc4`, `bf` passed as algorithm. Safe form uses
  `aes-256-gcm` or `chacha20-poly1305`.
- **ECB mode**: `crypto.createCipheriv('aes-128-ecb', ...)`.
- **MD5/SHA1 for integrity**: `crypto.createHash('md5')` or
  `crypto.createHash('sha1')` where the digest guards a
  security decision. Safe form uses `sha256` or higher.
- **Small RSA key**: `crypto.generateKeyPairSync('rsa',
  {modulusLength: 1024})`. Safe form uses 2048 or higher.

Defer to `references/javascript.md` for vulnerable-vs-safe
snippets.

### TypeScript

Same Node.js `crypto` module sinks as JavaScript apply.
Additionally:

- **Typed crypto wrappers** from `node:crypto` with weak
  algorithm string literals.
- Third-party libraries wrapping Node crypto with weak
  defaults.

Defer to `references/typescript.md` for vulnerable-vs-safe
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  weak algorithm at this location.
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
`crypto.weak_algorithm`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the sink and what an attacker can do>",
  "severity": "high",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-327"],
  "finding_type": ["vulnerability"],
  "rule_id": "crypto.weak_algorithm",
  "meta": {
    "title": "<short human title, e.g. 'ECB mode in AES encryption'>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding, per D19; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the sink>",
    "taint_source": "<request parameter or upstream variable, when traceable>",
    "reasoning": "<one sentence explaining why this is a weak algorithm>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual library observed in
the code. Examples of good remediation strings:

- **PyCryptodome DES**: `Replace DES with AES. Use
  Crypto.Cipher.AES.new(key, AES.MODE_GCM) for authenticated
  encryption.`
- **PHP mcrypt**: `The mcrypt extension is removed in PHP 7.2+.
  Use openssl_encrypt($data, 'aes-256-gcm', $key,
  OPENSSL_RAW_DATA, $iv, $tag) or sodium_crypto_secretbox().`
- **Node.js DES**: `Replace des with aes-256-gcm:
  crypto.createCipheriv('aes-256-gcm', key, iv). Use
  cipher.getAuthTag() for authenticated encryption.`
- **ECB mode**: `ECB does not provide semantic security.
  Switch to GCM (preferred for authenticated encryption) or
  CBC with a random IV.`
- **Small RSA key**: `Generate RSA keys of 2048 bits or
  higher. For new systems, prefer Ed25519 for signatures or
  X25519 for key exchange.`

Keep it two to four sentences. Vague guidance ("replace the
algorithm") is worse than no guidance.

## Common false positives

- **MD5/SHA1 for non-security checksums**: file integrity
  checks against known hashes, cache key generation, content
  deduplication. These are not security-sensitive uses.
- **Test or example code**: weak algorithms in test fixtures or
  documentation examples that do not run in production.
- **Constant algorithm strings in allowlists**: referencing
  algorithm names in configuration validation without invoking
  them.
- **Migration or compatibility code with mitigation**: code
  that reads legacy-encrypted data and immediately re-encrypts
  with a strong algorithm.

## References

- `references/python.md`: Python patterns for PyCryptodome,
  cryptography, hashlib, and RSA key generation.
- `references/php.md`: PHP patterns for mcrypt, OpenSSL,
  and RSA.
- `references/javascript.md`: Node patterns for crypto module.
- `references/typescript.md`: TypeScript patterns for node:crypto.
