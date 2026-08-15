---
name: tally-scan-misconfig-cors
description: >
  Scan the target repo for CORS misconfiguration defects. Detects CORS
  policies that permit any origin, combined with credentials enabled, or that
  reflect unauthenticated request origins. Emits findings shaped for Tally MCP
  submission (rule_id `misconfig.cors`, CWE-942, severity medium). Invoke when
  the user says "CORS", "cross-origin", "origin reflection", "check for CORS
  misconfiguration", or when dispatched by `tally-scan-external`.
---

# Tally scanner: CORS misconfiguration

Detects misconfigurations in Cross-Origin Resource Sharing (CORS) policies
where Access-Control headers permit overly permissive origins or reflect
unauthenticated source origins. Runs per-file in the target repo (as dispatched
by the `tally-scan-external` orchestrator, or standalone when the user invokes
this skill directly). Emits a JSON list of findings; the orchestrator or the
user submits them to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.cors` |
| Primary CWE | `CWE-942` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `CORSMisconfig` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 29.

## Detection matrix

### Python

- **django-cors-headers wildcard**: `CORS_ALLOW_ALL_ORIGINS = True` or
  `CORS_ORIGIN_WHITELIST` containing `*` as a value.
- **django-cors-headers with credentials**: `CORS_ALLOW_ALL_ORIGINS = True`
  combined with `CORS_ALLOW_CREDENTIALS = True` (regardless of origin list).
- **Flask-CORS wildcard origins**: `CORS(app, origins="*",
  supports_credentials=True)` or `CORS(app, origins=["*"],
  supports_credentials=True)`.
- **Starlette/FastAPI CORSMiddleware**: `CORSMiddleware` configured with
  `allow_origins=["*"]` and `allow_credentials=True`.
- **Manual header reflection**: setting `Access-Control-Allow-Origin` to the
  value of the `Origin` request header without validation against an allowlist.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel CORS wildcard**: `config/cors.php` with `allowed_origins =>
  ['*']` and `supports_credentials => true`.
- **Manual header reflection (PHP)**: `header('Access-Control-Allow-Origin: ' .
  $_SERVER['HTTP_ORIGIN'])` without validating the origin against trusted
  domains.
- **Manual CORS with credentials**: `header('Access-Control-Allow-Origin:
  *')` combined with `Access-Control-Allow-Credentials: true` (invalid but a
  misconfiguration).
- **DomDocument or manual XML processing**: permissive CORS on endpoints that
  parse XML or JSON from any origin.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express cors middleware wildcard**: `cors({origin: '*',
  credentials: true})` or `cors({origin: true, credentials: true})` with
  access to any origin.
- **Manual header reflection (Express)**: `res.setHeader(
  'Access-Control-Allow-Origin', req.headers.origin)` without validation.
- **Koa CORS middleware**: `cors({origin: '*', credentials: true})` or manual
  header reflection via `ctx.set('Access-Control-Allow-Origin',
  ctx.request.origin)`.
- **Manual wildcard**: `res.header('Access-Control-Allow-Origin', '*')` with
  other credentials headers enabled.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Express.js with typed cors**: same patterns as JavaScript; TypeScript
  type declarations do not prevent misconfiguration.
- **NestJS CORS config**: `@nestjs/common` CORS configuration with wildcard
  origin and credentials enabled.
- **Fastify CORS plugin**: `fastify.register(cors, {origin: '*',
  credentials: true})` or manual reflection.
- **Manual origin reflection**: custom CORS middleware that reflects the
  Origin header without validation.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the CORS configuration or header
  setting.
- `meta.code_snippet`: 2-6 lines of source containing the configuration.
- `meta.reasoning`: one sentence explaining why the configuration is
  overly permissive.
- When traceable: `meta.taint_source` naming the origin or request
  parameter that reaches the header.

Set `confidence`:

- `confirmed` when a wildcard origin is explicitly set alongside credentials,
  or when origin reflection is traced from a request header in the same file.
- `probable` when a permissive CORS configuration is detected but it is
  unclear whether credentials are enabled.
- `potential` when CORS is permissive but the finding is on a file that may
  not directly serve credentials.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.cors`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the misconfiguration, why it is risky,
  and how an attacker can exploit it>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-942"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.cors",
  "meta": {
    "title": "<short human title, e.g. 'CORS allows any origin with
    credentials enabled'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of configuration or header code>",
    "reasoning": "<one sentence explaining the misconfiguration at this
    location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual library or
framework observed in the code. Examples of good remediation strings:

- **django-cors-headers**: `Set CORS_ALLOW_ALL_ORIGINS = False and list
  specific trusted origins in CORS_ALLOWED_ORIGINS. Never combine wildcard
  origin with CORS_ALLOW_CREDENTIALS = True.`
- **Flask-CORS**: `Pass an explicit origins list: CORS(app, origins=[
  "https://app.example.com"], supports_credentials=True). Validate origins
  against a trusted allowlist.`
- **Express cors**: `Pass an explicit origin list or a validation function:
  cors({origin: ["https://app.example.com"], credentials: true}). Wildcard
  origin with credentials is rejected by browsers but signals
  misconfiguration.`
- **Laravel**: `Set allowed_origins to specific domains in
  config/cors.php. Remove the wildcard and list only trusted origins.`
- **Origin reflection**: `Validate the Origin header against an allowlist
  before reflecting it. Reject origins that do not match trusted domains.`
- **Fastify/NestJS**: `Provide an explicit origin list or a validation
  function. Do not reflect the Origin header without validation.`

Keep it two to four sentences. Vague guidance ("use an origin allowlist")
is worse than no guidance.

## Common false positives

- **CORS for development only**: CORS configured in dev/test/local files
  with wildcard and credentials enabled is a misconfiguration but lower risk
  if not deployed to production.
- **Wildcard origin without credentials**: `Access-Control-Allow-Origin: *`
  without credentials headers is permissive but not a credential-theft vector
  and may be intentional for public APIs.
- **Public API endpoints**: CORS set on public API endpoints serving any
  origin without sensitive data is not a vulnerability.
- **Origin validation in separate middleware**: CORS headers set via config
  but origin validation performed by a middleware or firewall rule not visible
  in the scanned file.
- **Constants and templates**: CORS configuration in module-level constants
  or template files representing safe development values with no user control.

## References

- `references/python.md`: Python patterns for django-cors-headers,
  Flask-CORS, Starlette/FastAPI CORSMiddleware.
- `references/php.md`: PHP patterns for Laravel cors config, manual headers,
  and origin reflection.
- `references/javascript.md`: Node.js patterns for Express cors middleware,
  Koa, and manual headers.
- `references/typescript.md`: TypeScript patterns for NestJS CORS, Express
  with typed config, and Fastify plugins.
