---
name: tally-scan-misconfig-csp
description: >
  Scan the target repo for Content Security Policy (CSP) misconfiguration.
  Detects missing CSP headers, CSP headers set to permissive values (wildcards,
  unsafe-inline, unsafe-eval), and disabled CSP in middleware. Emits findings
  shaped for Tally MCP submission (rule_id `misconfig.csp`, CWE-693, severity
  medium). Invoke when the user says "CSP", "content security policy", "check
  for CSP", or when dispatched by `tally-scan-external`.
---

# Tally scanner: CSP misconfiguration

Detects web framework configurations and explicit header directives that set
permissive Content Security Policy values or omit CSP entirely. Runs per-file
in the target repo (as dispatched by the `tally-scan-external` orchestrator, or
standalone when the user invokes this skill directly). Emits a JSON list of
findings; the orchestrator or the user submits them to Tally through the
`submit_finding` MCP tool.

Authoritative payload shape:
`../tally-scan-external/references/mcp-payload-shape.md`.

## Fixed skill identity

| Field | Value |
|---|---|
| `rule_id` | `misconfig.csp` |
| Primary CWE | `CWE-693` |
| OWASP 2025 category | `Security Misconfiguration` |
| Default severity | `medium` |
| Parent label (dedup) | `CSPMisconfig` |

Source: `docs/roadmap/TAL-148/taxonomy.md` T3 row 28, CWE override per
decision D27.

## Detection matrix

### Python

- **Django CSP middleware disabled**: `MIDDLEWARE` list does not include
  `'csp.middleware.CSPMiddleware'` or similar CSP middleware module.
- **Django CSP permissive**: `CSP_DEFAULT_SRC` set to `('*',)` or contains
  `'unsafe-inline'` or `'unsafe-eval'` without strict fallback sources.
- **Flask-Talisman disabled**: `Talisman` initialized with
  `content_security_policy=False`.
- **Flask-Talisman permissive**: `content_security_policy` dict contains
  `'default-src': '*'` or includes `'unsafe-inline'` or `'unsafe-eval'`.
- **Starlette middleware missing**: middleware stack does not include a CSP
  header injector, or CSP header is empty or contains wildcards.

Defer to `references/python.md` for vulnerable-vs-safe snippets.

### PHP

- **Laravel middleware missing**: security middleware does not set a
  restrictive Content-Security-Policy header in the response.
- **Laravel header permissive**: `header('Content-Security-Policy: ...')` call
  with `default-src *` or containing `unsafe-inline` or `unsafe-eval`.
- **Symfony NelmioSecurityBundle**: CSP config with `default_src: ['*']` or
  containing unsafe directives.
- **Manual header() permissive**: `header('Content-Security-Policy: ...')` with
  `*` in default-src or containing `unsafe-inline` or `unsafe-eval`.

Defer to `references/php.md` for vulnerable-vs-safe snippets.

### JavaScript

- **Express helmet disabled**: `contentSecurityPolicy: false` in helmet config.
- **Express helmet permissive**: helmet CSP config with `defaultSrc: ['*']` or
  containing `'unsafe-inline'` or `'unsafe-eval'`.
- **Koa helmet missing**: no CSP middleware in the middleware stack, or CSP
  header is empty.
- **Fastify helmet disabled**: `@fastify/helmet` registered with
  `contentSecurityPolicy: false`.

Defer to `references/javascript.md` for vulnerable-vs-safe snippets.

### TypeScript

- **Express helmet permissive**: same as JavaScript patterns above.
- **NestJS helmet permissive**: helmet integration with permissive CSP config.
- **Koa with TypeScript**: same as JavaScript Koa patterns.
- **Custom middleware permissive**: custom middleware setting CSP header with
  `default-src *` or containing `unsafe-inline` or `unsafe-eval`.

Defer to `references/typescript.md` for vulnerable-vs-safe snippets.

## Evidence requirements

Every finding must include:

- `file` and `line_number` pointing at the configuration line or middleware
  initialization.
- `meta.code_snippet`: 2-6 lines of source containing the misconfiguration.
- `meta.reasoning`: one sentence explaining why the CSP setting is permissive
  or missing.
- When the CSP value is hardcoded in the config or file: `meta.csp_value`
  naming the actual directive or configuration value observed.

Set `confidence`:

- `confirmed` when the CSP is explicitly set to a permissive value or missing
  from the middleware stack.
- `probable` when the configuration suggests CSP is not enforced but the exact
  setting is not visible in the scanned file.
- `potential` when the file indicates security headers may not be configured
  but the evidence is indirect.

## Output payload skeleton

Emit one JSON object per finding with these fixed fields for `misconfig.csp`:

```json
{
  "file": "<repo-relative path>",
  "line_number": <int>,
  "description": "<prose describing the permissive CSP or missing CSP,
  and the risk of XSS or injection attacks not being mitigated>",
  "severity": "medium",
  "confidence": "<confirmed|probable|potential>",
  "cwe": ["CWE-693"],
  "finding_type": ["misconfiguration"],
  "rule_id": "misconfig.csp",
  "meta": {
    "title": "<short human title, e.g. 'CSP default-src set to wildcard'>",
    "owasp_name": "Security Misconfiguration",
    "remediation": "<per-finding, per D19; see remediation guidance
    below>",
    "code_snippet": "<2-6 lines of source containing the configuration
    or middleware>",
    "csp_value": "<the actual CSP directive value observed, e.g.
    'default-src: *' or 'unsafe-inline', when visible>",
    "reasoning": "<one sentence explaining why the CSP is misconfigured
    at this location>"
  }
}
```

See `../tally-scan-external/references/mcp-payload-shape.md` for the full
field list and validator behavior.

## Remediation guidance for the scanner

Per D19, write `meta.remediation` inline based on the actual framework or
configuration observed in the code. Examples of good remediation strings:

- **Django**: `Add django-csp and configure CSP_DEFAULT_SRC =
  ("'self'",) in settings.py. For scripts and styles, set specific
  sources (e.g., CSP_SCRIPT_SRC, CSP_STYLE_SRC) instead of relying on
  default-src alone.`
- **Flask-Talisman**: `Pass a restrictive content_security_policy dict to
  Talisman(). Set default-src to "'self'" and add specific source origins
  only for required external resources.`
- **Express helmet**: `Enable contentSecurityPolicy in helmet config. Set
  defaultSrc to ["'self'"] and directives to trusted sources only. Remove
  wildcard sources.`
- **Laravel**: `Set a restrictive CSP header in security middleware.
  Configure default-src to 'self' and use specific directives for scripts
  and styles.`
- **Symfony**: `Configure CSP in NelmioSecurityBundle with restrictive
  directives. Set default_src to "'self'" and add only trusted script and
  style sources.`
- **PHP manual**: `Set a restrictive Content-Security-Policy header:
  header("Content-Security-Policy: default-src 'self'"). Add specific
  source origins for scripts and styles as needed.`
- **Koa**: `Use koa-helmet middleware to set CSP headers. Configure a
  restrictive default-src policy with specific directives for scripts and
  styles.`
- **Fastify**: `Register @fastify/helmet with a restrictive
  contentSecurityPolicy config. Set defaultSrc to ["'self'"] and trust
  only specific external origins.`

Keep it two to four sentences. Vague guidance ("set CSP") is worse than no
guidance.

## Common false positives

- **CSP configured in reverse proxy**: CSP headers set by nginx, Apache, or
  CDN configuration outside the app code are not visible in the scanned app
  files. Flag only the app configuration.
- **CSP in separate security middleware**: CSP set in a dedicated middleware
  module or middleware factory not visible in the current file. Verify the
  middleware is registered in the framework's middleware stack.
- **Report-only mode with enforcement**: Content-Security-Policy-Report-Only
  header alongside a strict enforcement policy (Content-Security-Policy) is
  safe when enforcement is the primary policy.
- **Development-only permissive settings**: Check file path for dev-only
  indicators (dev.py, development.js, .env.development) before flagging
  permissive CSP.
- **Test fixtures or mock configs**: Configuration in test files or fixtures
  (test_settings.py, __fixtures__/, mock config objects) does not affect
  production; do not flag unless the test data is shared with production.
- **Nonce or hash based policies**: CSP using nonces (`'nonce-*'`) or hashes
  (`'sha256-*'`) is safe even without strict default-src; the nonce or hash
  whitelists specific inline scripts or styles.

## References

- `references/python.md`: Python patterns for Django, Flask-Talisman, Starlette.
- `references/php.md`: PHP patterns for Laravel, Symfony, manual header calls.
- `references/javascript.md`: Node patterns for Express helmet, Koa, Fastify.
- `references/typescript.md`: TypeScript patterns for NestJS, Express with
  TypeScript, custom middleware.
