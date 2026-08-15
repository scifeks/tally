---
name: tally-scan-misconfig-security-headers
description: >
  Scan the target repo for missing security response headers. Detects
  applications omitting critical headers (X-Content-Type-Options,
  X-Frame-Options, Strict-Transport-Security, Referrer-Policy,
  Permissions-Policy) that protect browsers from clickjacking, MIME
  sniffing, and credential leakage. Emits findings shaped for Tally MCP
  submission (rule_id `misconfig.security_headers`, CWE-693, severity
  low). Invoke when the user says "security headers", "missing headers",
  "check for security headers", or when dispatched by
  `tally-scan-external`.
---

# Tally scanner: missing security response headers

Detects HTTP response handling that omits critical security headers
protecting the browser and users against clickjacking, MIME sniffing,
credential leakage via referrer, and unwanted feature access. Runs
per-file in the target repo (as dispatched by the `tally-scan-external`
orchestrator, or standalone when the user invokes this skill directly).
Emits a JSON list of findings; the orchestrator or the user submits them
to Tally through the `submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.security_headers` |
| Primary CWE | `CWE-693` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `low` |
| Parent label (dedup) | `MissingSecurityHeaders` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 30.

## Detection matrix

### Python

- **Django missing SECURE_ settings**: `SECURE_HSTS_SECONDS` not set or
  set to 0; `SECURE_CONTENT_TYPE_NOSNIFF` is False; `SECURE_REFERRER_POLICY`
  missing; `X_FRAME_OPTIONS` not configured in settings.py.
- **Flask without Talisman**: application lacks Flask-Talisman or
  equivalent middleware that injects security headers on every response.
- **Manual response headers missing**: response-building code that calls
  `make_response()`, `jsonify()`, or modifies response objects without
  setting X-Content-Type-Options, X-Frame-Options, or HSTS headers.
- **Starlette without middleware**: Starlette applications without
  middleware that applies security headers to all responses.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel missing middleware**: application does not apply a middleware
  that injects security headers; framework does not set these by default.
- **Symfony without NelmioSecurityBundle**: application lacks
  NelmioSecurityBundle configuration for `x_content_type_options`,
  `x_frame_options`, HSTS, or Referrer-Policy headers.
- **Manual header() calls missing headers**: response middleware or
  controller methods that call `header()` without setting
  X-Content-Type-Options, X-Frame-Options, or HSTS.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express without helmet or disabled protections**: helmet not installed
  or specific header protections explicitly disabled (e.g.,
  `helmet({hsts: false, frameguard: false})`).
- **Koa without koa-helmet**: application lacks `koa-helmet` or equivalent
  middleware injecting security headers.
- **Fastify without @fastify/helmet**: application lacks
  `@fastify/helmet` plugin that sets security headers on responses.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **NestJS without helmet**: `helmet` not applied in `main.ts` or app
  configuration; NestJS does not set security headers by default.
- **Express with typed config**: same patterns as JavaScript; helmet not
  installed or specific protections explicitly disabled.
- **Fastify with TypeScript**: same patterns as JavaScript; `@fastify/helmet`
  not installed or properly configured.
- **Custom middleware omitting headers**: response middleware that does
  not set X-Content-Type-Options, X-Frame-Options, or HSTS headers.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the response-handling location
  (middleware, settings file, or route handler).
- `meta.code_snippet`: 2-6 lines of source showing where security headers
  should be set but are not.
- `meta.reasoning`: one sentence explaining why this location is missing
  critical headers.
- When traceable: `meta.taint_source` naming the response object or
  middleware context that reaches this location.

Set `confidence`:

- `confirmed` when the code pattern matches a known vulnerable framework
  configuration or middleware pattern, and the file contains no
  header-setting logic.
- `probable` when the response-building code is clearly visible but headers
  are absent, and no parallel file in the repo is known to set them
  centrally.
- `potential` when the pattern is suspicious but headers might be set by
  a reverse proxy or CDN outside this file.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for
`misconfig.security_headers`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the missing header, the risk, and what
  an attacker can achieve by exploiting this misconfiguration>",
  "severity": "low",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-693"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.security_headers",
  "meta": {
    "title": "<short human title, e.g. 'Missing X-Frame-Options header
    in Flask response middleware'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source showing missing header setup>",
    "reasoning": "<one sentence explaining the defect at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual framework
observed in the code. Examples of good remediation strings:

- **Django**: `Set SECURE_HSTS_SECONDS to at least 31536000,
  SECURE_CONTENT_TYPE_NOSNIFF = True, and SECURE_REFERRER_POLICY =
  'strict-origin-when-cross-origin' in settings.py.`
- **Flask-Talisman**: `Install Flask-Talisman and call Talisman(app). It
  sets X-Content-Type-Options, X-Frame-Options, and HSTS headers by
  default on all responses.`
- **Express helmet**: `Call app.use(helmet()) without disabling individual
  protections. Helmet sets X-Content-Type-Options, X-Frame-Options, and
  HSTS headers on every response by default.`
- **Laravel middleware**: `Create a middleware that adds
  X-Content-Type-Options: nosniff, X-Frame-Options: DENY, and
  Strict-Transport-Security headers to every response. Apply it globally
  in app/Http/Kernel.php.`
- **Symfony NelmioSecurityBundle**: `Configure NelmioSecurityBundle in
  config/packages/nelmio_security.yaml with x_content_type_options,
  x_frame_options, and forced_https settings.`
- **NestJS helmet**: `Import helmet in main.ts: app.use(helmet()). Helmet
  middleware sets security headers on all responses by default.`

Keep it two to four sentences. Name the library and the specific safe
pattern. Vague guidance ("add security headers") is worse than no
guidance.

## Common false positives

- **Headers set by reverse proxy or CDN**: if Nginx, Apache, Cloudflare,
  or other reverse proxy injects headers, the application code may not
  set them explicitly. Check proxy configuration before flagging.
- **Headers set in a separate middleware file**: if security headers are
  injected by a middleware that runs globally but is not in the current
  file, defer to confirm the middleware exists and is applied. Do not flag
  every response handler when a single global middleware applies headers.
- **Test or development-only response builders**: if the code only runs
  in test or dev environments and not in production, consider downgrading
  severity or confidence.
- **Static file servers or asset handlers**: security headers are less
  critical on routes serving only static assets or read-only resources;
  if the endpoint sets appropriate Cache-Control headers, that may be
  sufficient.
- **CSP-related findings**: Content-Security-Policy header is handled by
  the separate `misconfig.csp` skill, not this one. Do not flag CSP
  absence here.

## References

- `references/python.md`: Python patterns for Django, Flask-Talisman,
  Starlette.
- `references/php.md`: PHP patterns for Laravel, Symfony
  NelmioSecurityBundle, manual header() calls.
- `references/javascript.md`: Node patterns for Express helmet, Koa,
  Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, Express, and
  Fastify with helmet.
