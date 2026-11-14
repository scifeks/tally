---
name: tally-scan-crypto-hardcoded-secrets
description: >
  Scan the target repo for hardcoded credentials, API keys,
  tokens, and private keys in source code. Detects string
  literals assigned to variables with secret-indicating
  names (password, api_key, secret, token), AWS access
  keys (AKIA prefix), connection strings with embedded
  credentials, and PEM-encoded private keys. Emits
  findings shaped for Tally MCP submission (rule_id
  crypto.hardcoded_secrets, CWE-798, severity critical).
  Invoke when the user says "hardcoded secret",
  "hardcoded password", "credentials in source",
  "check for API keys", or when dispatched by
  tally-scan-external.
---

# Tally scanner: hardcoded credentials or keys

Detects credentials, API keys, tokens, and private keys hardcoded as string
literals in source code. Runs per-file in the target repo (as dispatched by
the `tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `crypto.hardcoded_secrets` |
| Primary CWE | `CWE-798` |
| Secondary CWE | `CWE-259` |
| OWASP 2025 category | `Cryptographic Failures` |
| Default severity | `critical` |
| Parent label (dedup) | `HardcodedSecret` |


## Detection matrix

### Python

- **Secret-named variable with string literal**: `API_KEY = "sk-..."`,
  `SECRET_KEY = "..."`, `password = "admin123"`, `DB_PASSWORD = "..."`,
  `token = "ghp_..."`, `auth_token = "Bearer ..."`.
- **AWS access keys**: `aws_access_key_id = "AKIA..."` or
  `aws_secret_access_key = "..."` as string literals.
- **Connection strings with passwords**:
  `"postgresql://user:pass@host/db"`,
  `"mysql://root:password@localhost/mydb"`.
- **Django SECRET_KEY hardcoded**: `SECRET_KEY = "..."` in
  `settings.py` instead of `os.environ`.
- **PEM private keys**: multi-line string containing
  `-----BEGIN RSA PRIVATE KEY-----` or similar PEM headers.
- **Config dicts with secret values**: `{"password": "...",
  "api_key": "..."}` in source code.

Read `references/python.md` for vulnerable-vs-safe code patterns.

### PHP

- **Secret-named variable**: `$apiKey = "sk_live_..."`,
  `$password = "admin"`, `$dbPassword = "..."`.
- **define/const with secret**: `define('DB_PASSWORD',
  'hunter2')`, `const API_KEY = '...'`.
- **Config arrays with secrets**: `'password' => 'admin123'`
  in config files instead of `env()`.
- **DSN with credentials**: `"mysql:host=...;password=..."`
  as a string literal.

Read `references/php.md` for vulnerable-vs-safe code patterns.

### JavaScript

- **Secret-named const/let/var**: `const API_KEY = "..."`,
  `let password = "admin"`, `var token = "..."`.
- **Firebase config with secrets**: Firebase config objects
  with `apiKey`, `authDomain` hardcoded in source.
- **Fallback literals**: `process.env.SECRET || "default123"`
  where the fallback is a real secret.
- **Connection strings**: `"mongodb://user:pass@host/db"`.

Read `references/javascript.md` for vulnerable-vs-safe code
snippets.

### TypeScript

Same sinks as JavaScript. Additionally:

- **Typed config objects** with string literal values for
  secret properties.
- **Interface implementations** with hardcoded credentials.

Read `references/typescript.md` for vulnerable-vs-safe code
snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the sink call.
- `meta.code_snippet`: 2-6 lines of source containing the sink.
- `meta.reasoning`: one sentence explaining why the pattern is a
  hardcoded secret at this location.
- When the secret usage or purpose is clear in the same file:
  `meta.taint_source` naming the variable or context that contains
  the secret.

Set `confidence`:

- `confirmed` when a string literal is assigned to a variable or
  constant with a secret-indicating name, or the string matches a
  known secret pattern (API key prefix, PEM header).
- `probable` when the variable name suggests secrecy but the value
  is not obviously a real secret.
- `potential` when the pattern is suspicious but the context is
  unclear.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`crypto.hardcoded_secrets`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the secret, where it is, and the risk>",
  "severity": "critical",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-798", "CWE-259"],
  "finding_type": ["secret"],
  "rule_id": "crypto.hardcoded_secrets",
  "meta": {
    "title": "<short human title, e.g. 'Hardcoded AWS access key in config'>",
    "owasp_name": "Cryptographic Failures",
    "remediation": "<per-finding remediation; see remediation guidance below>",
    "code_snippet": "<2-6 lines of source containing the secret>",
    "taint_source": "<variable name or context, when clear>",
    "reasoning": "<one sentence explaining why this is a hardcoded secret>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for
the full field list and validator behavior.

## Remediation guidance for the scanner

Write `meta.remediation` inline based on the actual
library or pattern observed. Examples of good remediation strings:

- **Python env var**: `Load the secret from the environment:
  api_key = os.environ["API_KEY"]. Use python-dotenv for
  local development.`
- **Django SECRET_KEY**: `Set SECRET_KEY =
  os.environ["DJANGO_SECRET_KEY"] in settings.py. Generate a
  random key with django.core.management.utils
  .get_random_secret_key() and store it in .env.`
- **PHP env()**: `Use Laravel's env() helper: 'password' =>
  env('DB_PASSWORD'). Store the value in .env, which is
  gitignored.`
- **Node.js process.env**: `Load from environment:
  const apiKey = process.env.API_KEY. Use dotenv for local
  development. Never commit .env files.`
- **AWS credentials**: `Use IAM instance profiles, environment
  variables, or the AWS credentials file (~/.aws/credentials).
  Never hardcode AKIA keys in source.`
- **PEM private keys**: `Store private keys in files outside
  the repo, referenced by path through an environment variable
  or a secrets manager.`

Keep it two to four sentences. Vague guidance ("move to env
var") is worse than no guidance.

## Common false positives

- **Placeholder/example values**: `password = "changeme"`,
  `API_KEY = "your-key-here"`, `token = "xxx"`. These are
  placeholders, not real secrets.
- **Test fixtures**: hardcoded credentials in test setup for
  local test databases (e.g., `password = "test"` in a
  `conftest.py`).
- **Documentation strings**: secret-like strings in comments,
  docstrings, or README examples.
- **Environment variable reads**: `os.environ["API_KEY"]`,
  `process.env.SECRET`, `env('DB_PASSWORD')` are safe because
  the value comes from the environment, not the source.
- **Hash constants**: bcrypt hashes (`$2y$...`) or SHA hashes
  stored as comparison values are not secrets; they are
  derived values.

## References

- `references/python.md`: Python patterns for API keys, Django
  SECRET_KEY, AWS credentials, connection strings, PEM keys.
- `references/php.md`: PHP patterns for variables, constants,
  Laravel config, connection strings.
- `references/javascript.md`: Node patterns for const/let/var,
  Firebase config, fallback literals, connection strings.
- `references/typescript.md`: TypeScript patterns for typed
  config objects and interface implementations.
